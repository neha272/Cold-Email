"""Main orchestration logic for daily runs."""

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from cold_emailer.composer import create_composer_from_config
from cold_emailer.config import EnvSettings
from cold_emailer.export import export_prospects_to_excel
from cold_emailer.ingestion import ingest_prospects
from cold_emailer.mailer.imap_reply_detector import create_reply_detector_from_config
from cold_emailer.mailer.smtp_sender import create_smtp_sender_from_config
from cold_emailer.state_store.db import create_database_engine, get_session, init_database
from cold_emailer.state_store.models import MessageEventType, ProspectStatus
from cold_emailer.state_store.repo import MessageEventRepository, ProspectRepository
from cold_emailer.utils import get_logger

logger = get_logger(__name__)


class Orchestrator:
    """Main orchestrator for cold-email automation."""

    def __init__(
        self,
        settings: Any,
        env_settings: EnvSettings,
        sequences: dict[str, Any],
        dry_run: bool = False,
    ) -> None:
        """
        Initialize orchestrator.

        Args:
            settings: Application settings
            env_settings: Environment settings (SMTP/IMAP)
            sequences: Sequence definitions
            dry_run: Enable dry-run mode
        """
        self.settings = settings
        self.env_settings = env_settings
        self.sequences = sequences
        self.dry_run = dry_run

        # Initialize components
        self.engine = create_database_engine(
            db_path=settings.database.path, echo=settings.database.echo
        )
        self.composer = create_composer_from_config(settings)
        self.smtp_sender = create_smtp_sender_from_config(env_settings) if not dry_run else None
        self.reply_detector = (
            create_reply_detector_from_config(env_settings) if not dry_run else None
        )

        # Throttling state
        self.daily_sent_count = 0
        self.last_send_time: datetime | None = None

    def _check_throttle_limits(self) -> bool:
        """
        Check if we can send more emails based on throttling limits.

        Returns:
            True if we can send, False if throttled
        """
        # Check daily limit
        if self.daily_sent_count >= self.settings.throttling.daily_max:
            logger.warning("Daily email limit reached", limit=self.settings.throttling.daily_max)
            return False

        # Check per-minute limit
        if self.last_send_time:
            time_since_last = (datetime.utcnow() - self.last_send_time).total_seconds()
            min_interval = 60 / self.settings.throttling.per_minute_limit
            if time_since_last < min_interval:
                wait_time = min_interval - time_since_last
                logger.debug("Throttling: waiting", seconds=wait_time)
                time.sleep(wait_time)

        return True

    def _is_within_send_window(self) -> bool:
        """
        Check if current time is within send window.
        Uses local time to match user's timezone expectations.

        Returns:
            True if within window
        """
        now = datetime.now()  # Use local time instead of UTC
        current_time = now.strftime("%H:%M")

        start = self.settings.throttling.send_window_start
        end = self.settings.throttling.send_window_end

        return start <= current_time <= end

    def _calculate_next_action_time(self, sequence_id: str) -> datetime | None:
        """
        Calculate next_action_at based on sequence configuration.

        Args:
            sequence_id: ID of the sequence

        Returns:
            datetime object for next action, or None for immediate sending
        """
        # Get sequence configuration
        sequences_dict = self.sequences.get("sequences", {})
        sequence_config = sequences_dict.get(sequence_id, {})
        schedule_time = sequence_config.get("schedule_initial_at")

        if not schedule_time:
            # No scheduling configured, send immediately (when campaign runs)
            return None

        try:
            # Parse the time string (HH:MM format)
            hours, minutes = map(int, schedule_time.split(":"))

            # Get current time
            now = datetime.now()

            # Create scheduled datetime for today at specified time
            scheduled_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)

            # If the time has already passed today, schedule for tomorrow
            if scheduled_time <= now:
                scheduled_time += timedelta(days=1)

            logger.info(
                "Calculated next action time",
                sequence_id=sequence_id,
                schedule_time=schedule_time,
                next_action_at=scheduled_time.isoformat(),
            )

            return scheduled_time

        except Exception as e:
            logger.error(
                "Failed to parse schedule_initial_at",
                sequence_id=sequence_id,
                schedule_time=schedule_time,
                error=str(e),
            )
            # Fall back to immediate sending
            return None

    def ingest_prospects_file(
        self, file_path: Path, reset_state: bool = False, manifest: Any | None = None
    ) -> tuple[int, int, list[dict[str, Any]]]:
        """
        Ingest prospects from file.

        Args:
            file_path: Path to prospects file
            reset_state: Reset state for existing prospects

        Returns:
            Tuple of (created_count, updated_count, errors)
        """
        # Ensure database is initialized
        init_database(self.engine)

        # Get resumes directory from settings
        resumes_dir = Path(self.settings.paths.resumes_dir)

        with get_session(self.engine) as session:
            repo = ProspectRepository(session)
            created, updated, errors = ingest_prospects(
                file_path=file_path,
                resumes_dir=resumes_dir,
                manifest=manifest,
                repo=repo,
                reset_state=reset_state,
            )

            # Set next_action_at for NEW prospects based on sequence configuration
            all_prospects = repo.get_all()
            scheduled_count = 0
            for prospect in all_prospects:
                if prospect.status == ProspectStatus.NEW.value and prospect.next_action_at is None:
                    # Calculate scheduled time based on sequence config
                    next_action_at = self._calculate_next_action_time(
                        prospect.sequence_id or "default"
                    )
                    if next_action_at:
                        prospect.next_action_at = next_action_at
                        scheduled_count += 1

            if scheduled_count > 0:
                session.commit()
                logger.info(
                    "Scheduled NEW prospects based on sequence configuration",
                    scheduled_count=scheduled_count,
                )

            return created, updated, errors

    def detect_replies(self) -> int:
        """
        Detect replies for all prospects with outbound messages.

        Returns:
            Number of replies detected
        """
        if self.dry_run:
            logger.info("Reply detection skipped (dry-run mode)")
            return 0

        if not self.reply_detector:
            logger.info("Reply detection skipped (IMAP not configured)")
            return 0

        replies_detected = 0

        with get_session(self.engine) as session:
            prospect_repo = ProspectRepository(session)
            event_repo = MessageEventRepository(session)

            # Get all prospects with outbound message IDs and non-terminal status
            prospects = prospect_repo.get_all()
            prospects_with_messages = [
                p for p in prospects if p.thread_key and not p.is_terminal_status()
            ]

            if not prospects_with_messages:
                logger.info("No prospects with outbound messages to check")
                return 0

            # Group by outbound message ID
            outbound_ids: list[str] = []
            prospect_by_message_id: dict[str, Any] = {}
            for prospect in prospects_with_messages:
                if prospect.thread_key:
                    outbound_ids.append(prospect.thread_key)
                    prospect_by_message_id[prospect.thread_key] = prospect

            # Detect replies by Message-ID
            replies = self.reply_detector.detect_replies_by_message_id(outbound_ids)

            # Process detected replies
            for outbound_id, reply_list in replies.items():
                if reply_list:
                    prospect = prospect_by_message_id.get(outbound_id)  # type: ignore[assignment]
                    if prospect:
                        # Update prospect status
                        prospect_repo.update_status(prospect.id, ProspectStatus.REPLIED)
                        prospect_repo.update_next_action(prospect.id, None)  # type: ignore[arg-type]

                        # Log reply event
                        for reply_info in reply_list:
                            event_repo.create(
                                {
                                    "prospect_id": prospect.id,
                                    "event_type": MessageEventType.REPLY_DETECTED.value,
                                    "subject": reply_info.get("subject"),
                                    "outbound_message_id": outbound_id,
                                    "meta_json": str(reply_info),
                                }
                            )
                            replies_detected += 1

                        logger.info(
                            "Reply detected for prospect",
                            prospect_id=str(prospect.id),
                            email=prospect.email,
                            outbound_id=outbound_id,
                        )

            # Fallback detection for prospects without Message-ID
            for prospect in prospects_with_messages:
                if not prospect.thread_key:
                    # Get last sent message subject
                    last_event = event_repo.get_by_prospect_id(prospect.id, limit=1)
                    if last_event:
                        last_subject = last_event[0].subject
                        if last_subject:
                            fallback_replies = self.reply_detector.detect_reply_fallback(
                                prospect_email=prospect.email,
                                original_subject=last_subject,
                            )
                            if fallback_replies:
                                prospect_repo.update_status(prospect.id, ProspectStatus.REPLIED)
                                prospect_repo.update_next_action(prospect.id, None)  # type: ignore[arg-type]
                                for reply_info in fallback_replies:
                                    event_repo.create(
                                        {
                                            "prospect_id": prospect.id,
                                            "event_type": MessageEventType.REPLY_DETECTED.value,
                                            "subject": reply_info.get("subject"),
                                            "meta_json": str(reply_info),
                                        }
                                    )
                                    replies_detected += 1

            # Additional check: Detect replies by email address for ALL active prospects
            # This catches replies even if Message-ID matching fails
            all_active_prospects = [
                p for p in prospect_repo.get_all() if not p.is_terminal_status() and p.email
            ]

            # Get unique prospect emails
            prospect_emails = list({p.email for p in all_active_prospects})

            if prospect_emails:
                # Check for replies from any prospect email
                for prospect_email in prospect_emails:
                    # Get prospects with this email
                    prospects_for_email = [
                        p for p in all_active_prospects if p.email == prospect_email
                    ]
                    if not prospects_for_email:
                        continue

                    # Get last sent subject for any of these prospects
                    last_subject = None
                    for p in prospects_for_email:
                        events = event_repo.get_by_prospect_id(p.id, limit=1)
                        if events and events[0].subject:
                            last_subject = events[0].subject
                            break

                    if last_subject:
                        # Check for replies from this email address
                        email_replies = self.reply_detector.detect_reply_fallback(
                            prospect_email=prospect_email,
                            original_subject=last_subject,
                        )

                        if email_replies:
                            # Mark all prospects with this email as REPLIED
                            for prospect in prospects_for_email:
                                if prospect.status != ProspectStatus.REPLIED.value:
                                    prospect_repo.update_status(prospect.id, ProspectStatus.REPLIED)
                                    prospect_repo.update_next_action(prospect.id, None)  # type: ignore[arg-type]

                                    # Log reply event
                                    for reply_info in email_replies:
                                        event_repo.create(
                                            {
                                                "prospect_id": prospect.id,
                                                "event_type": MessageEventType.REPLY_DETECTED.value,
                                                "subject": reply_info.get("subject"),
                                                "meta_json": str(reply_info),
                                            }
                                        )
                                    replies_detected += len(email_replies)

                                    logger.info(
                                        "Reply detected by email address",
                                        prospect_id=str(prospect.id),
                                        email=prospect.email,
                                    )

        return replies_detected

    def get_due_prospects(self) -> list[Any]:
        """
        Get prospects that are due for action.

        Returns:
            List of Prospect objects
        """
        with get_session(self.engine) as session:
            repo = ProspectRepository(session)
            now = datetime.utcnow()
            due = repo.get_due_prospects(now, limit=self.settings.throttling.daily_max)
            return due

    def send_email_to_prospect(
        self, prospect: Any, template_name: str, subject: str, step: int
    ) -> tuple[bool, str | None]:
        """
        Send email to a prospect.

        Args:
            prospect: Prospect object
            template_name: Template to use
            subject: Subject line (may contain template variables)
            step: Follow-up step number

        Returns:
            Tuple of (success, message_id)
        """
        with get_session(self.engine) as session:
            prospect_repo = ProspectRepository(session)
            event_repo = MessageEventRepository(session)

            # Merge prospect into this session to avoid detached instance errors
            prospect = session.merge(prospect)

            # Get template variables
            variables = self.composer.get_template_variables_from_prospect(prospect, self.sequences)

            # Compose email
            try:
                msg = self.composer.compose_email(
                    template_name=template_name,
                    to_email=prospect.email,
                    to_name=prospect.full_name,
                    variables=variables,
                    subject_override=subject,
                    reply_to=self.settings.email.reply_to,
                )

                # Validate resume attachment
                from cold_emailer.attachments import find_resume_file, validate_resume_file

                resume_path = Path(prospect.resume_path) if prospect.resume_path else None

                # If resume_path is not set, try to find it by resume_id
                if not resume_path and prospect.resume_id:
                    resumes_dir = Path(self.settings.paths.resumes_dir)
                    if not resumes_dir.is_absolute():
                        # Resolve relative to current working directory
                        resumes_dir = Path.cwd() / resumes_dir
                    is_valid, error_msg, resume_info = find_resume_file(
                        prospect.resume_id, resumes_dir
                    )
                    if is_valid and resume_info:
                        resume_path = Path(resume_info.get("absolute_path"))  # type: ignore[arg-type]
                        # Update prospect with found resume_path if it was missing
                        if not prospect.resume_path:
                            prospect.resume_path = str(resume_path)
                            prospect.resume_sha256 = resume_info.get("sha256")
                            session.flush()
                    else:
                        logger.warning(
                            "Could not find resume file by resume_id",
                            prospect_id=str(prospect.id),
                            resume_id=prospect.resume_id,
                            error=error_msg,
                        )

                if resume_path:
                    expected_sha256 = None if self.dry_run else prospect.resume_sha256
                    is_valid, error = validate_resume_file(resume_path, expected_sha256)
                    if not is_valid:
                        logger.error(
                            "Resume validation failed, not sending",
                            prospect_id=str(prospect.id),
                            error=error,
                        )
                        event_repo.create(
                            {
                                "prospect_id": prospect.id,
                                "event_type": MessageEventType.SEND_FAIL.value,
                                "subject": subject,
                                "template_id": template_name,
                                "meta_json": f'{{"error": "{error}"}}',
                            }
                        )
                        prospect_repo.update_status(prospect.id, ProspectStatus.ERROR)
                        prospect_repo.update_next_action(prospect.id, None)  # type: ignore[arg-type]
                        return False, None
                else:
                    logger.error(
                        "Resume path not found and could not locate by resume_id",
                        prospect_id=str(prospect.id),
                        resume_id=prospect.resume_id,
                    )
                    event_repo.create(
                        {
                            "prospect_id": prospect.id,
                            "event_type": MessageEventType.SEND_FAIL.value,
                            "subject": subject,
                            "template_id": template_name,
                            "meta_json": '{"error": "Resume file not found: None"}',
                        }
                    )
                    prospect_repo.update_status(prospect.id, ProspectStatus.ERROR)
                    prospect_repo.update_next_action(prospect.id, None)  # type: ignore[arg-type]
                    return False, None

                # Log send attempt (only in live mode, not dry-run)
                message_id = msg.get("Message-ID", "").strip("<>")
                if not self.dry_run:
                    event_repo.create(
                        {
                            "prospect_id": prospect.id,
                            "event_type": MessageEventType.SEND_ATTEMPT.value,
                            "subject": subject,
                            "template_id": template_name,
                            "outbound_message_id": message_id,
                        }
                    )

                # Send email
                if self.smtp_sender and resume_path:
                    # Use resume filename from prospect data or default to resume_id
                    display_name = getattr(prospect, "resume_display_name", None) or str(
                        getattr(prospect, "resume_id", "")
                    )
                    # Format as "Resume-Name.pdf" replacing spaces with hyphens
                    if display_name and not display_name.endswith(".pdf"):
                        resume_filename = f"Resume-{display_name.replace(' ', '_')}.pdf"
                    else:
                        resume_filename = display_name

                    success, sent_message_id, attachment_sha256, error = (
                        self.smtp_sender.send_with_attachment(
                            msg=msg,
                            attachment_path=resume_path,
                            attachment_filename=resume_filename,
                            dry_run=self.dry_run,
                        )
                    )
                elif self.smtp_sender:
                    success, sent_message_id, error = self.smtp_sender.send(
                        msg, dry_run=self.dry_run
                    )
                    attachment_sha256 = None
                else:
                    # Dry-run mode
                    success, sent_message_id, attachment_sha256, error = (
                        True,
                        message_id,
                        prospect.resume_sha256,
                        None,
                    )

                if success:
                    # In dry-run mode, don't update database state - only log what would happen
                    if not self.dry_run:
                        # Update prospect state
                        if step == 0:
                            new_status = ProspectStatus.SENT_INITIAL
                        elif step == 1:
                            new_status = ProspectStatus.FOLLOWUP_1_SENT
                        elif step == 2:
                            new_status = ProspectStatus.FOLLOWUP_2_SENT
                        else:
                            new_status = ProspectStatus.COMPLETED

                        # Update prospect state - ensure changes are flushed
                        updated_prospect = prospect_repo.update_status(prospect.id, new_status)
                        prospect_repo.update_followup_step(prospect.id, step + 1)
                        prospect_repo.update_next_action(
                            prospect.id, None
                        )  # Will be set by sequence
                        prospect_repo.update_last_sent_at(prospect.id)  # Update last sent timestamp

                        # Store thread key
                        if sent_message_id:
                            if updated_prospect:
                                updated_prospect.thread_key = sent_message_id
                            else:
                                # Fallback: update directly
                                prospect = session.get(type(prospect), prospect.id)
                                if prospect:
                                    prospect.thread_key = sent_message_id

                        # Flush changes to ensure they're persisted
                        session.flush()

                        # Log success
                        event_repo.create(
                            {
                                "prospect_id": prospect.id,
                                "event_type": MessageEventType.SEND_SUCCESS.value,
                                "subject": subject,
                                "template_id": template_name,
                                "outbound_message_id": sent_message_id,
                                "attachment_sha256": attachment_sha256,
                            }
                        )

                        # Update next action time based on sequence
                        step_config = self.composer.get_sequence_step(
                            self.sequences, prospect.sequence_id, step + 1
                        )
                        if step_config:
                            wait_days = step_config.get("wait_days", 0)
                            next_action = datetime.utcnow() + timedelta(days=wait_days)
                            prospect_repo.update_next_action(prospect.id, next_action)  # type: ignore[arg-type]
                        else:
                            # No more steps, mark as completed
                            prospect_repo.update_status(prospect.id, ProspectStatus.COMPLETED)
                            prospect_repo.update_next_action(prospect.id, None)  # type: ignore[arg-type]
                    else:
                        # Dry-run mode: only log what would happen (don't create events or update state)
                        logger.info(
                            "Dry-run: Would send email",
                            prospect_id=str(prospect.id),
                            step=step,
                            subject=subject,
                            template=template_name,
                        )

                    self.daily_sent_count += 1
                    self.last_send_time = datetime.utcnow()

                    logger.info(
                        "Email sent successfully",
                        prospect_id=str(prospect.id),
                        email=prospect.email,
                        step=step,
                        dry_run=self.dry_run,
                    )

                    return True, sent_message_id
                else:
                    # Send failed
                    event_repo.create(
                        {
                            "prospect_id": prospect.id,
                            "event_type": MessageEventType.SEND_FAIL.value,
                            "subject": subject,
                            "template_id": template_name,
                            "outbound_message_id": sent_message_id,
                            "meta_json": f'{{"error": "{error}"}}',
                        }
                    )
                    prospect_repo.update_status(prospect.id, ProspectStatus.ERROR)
                    prospect_repo.update_next_action(prospect.id, None)

                    logger.error(
                        "Failed to send email",
                        prospect_id=str(prospect.id),
                        error=error,
                    )

                    return False, sent_message_id

            except Exception as e:
                logger.error("Error sending email", prospect_id=str(prospect.id), error=str(e))
                event_repo.create(
                    {
                        "prospect_id": prospect.id,
                        "event_type": MessageEventType.SEND_FAIL.value,
                        "subject": subject,
                        "template_id": template_name,
                        "meta_json": f'{{"error": "{str(e)}"}}',
                    }
                )
                prospect_repo.update_status(prospect.id, ProspectStatus.ERROR)
                return False, None

    def run_daily(
        self,
        prospects_file: Path | None = None,
        manifest: Any | None = None,
    ) -> dict[str, Any]:
        """
        Run daily automation workflow.

        Args:
            prospects_file: Optional path to prospects file (for ingestion)

        Returns:
            Summary dictionary with run statistics
        """
        summary: dict[str, Any] = {
            "ingested": {"created": 0, "updated": 0, "errors": []},
            "replies_detected": 0,
            "emails_sent": 0,
            "emails_failed": 0,
            "throttled": 0,
        }

        logger.info("Starting daily run", dry_run=self.dry_run)
        summary["dry_run"] = self.dry_run

        # Step 1: Ingest prospects if file provided
        if prospects_file:
            logger.info("Ingesting prospects", file=str(prospects_file))
            created, updated, errors = self.ingest_prospects_file(prospects_file, manifest=manifest)
            summary["ingested"]["created"] = created
            summary["ingested"]["updated"] = updated
            summary["ingested"]["errors"] = errors

        # Step 2: Detect replies
        logger.info("Detecting replies")
        replies_detected = self.detect_replies()
        summary["replies_detected"] = replies_detected

        # Step 3: Get due prospects
        if not self._is_within_send_window():
            logger.info("Outside send window, skipping send queue")
            return summary

        due_prospects = self.get_due_prospects()
        logger.info("Found due prospects", count=len(due_prospects))

        # Step 4: Send emails
        for prospect in due_prospects:
            # Check throttling
            if not self._check_throttle_limits():
                summary["throttled"] += 1
                continue

            # Get sequence step configuration
            step_config = self.composer.get_sequence_step(
                self.sequences, prospect.sequence_id, prospect.followup_step
            )

            if not step_config:
                # No more steps in sequence - mark as COMPLETED
                logger.info(
                    "No more sequence steps, marking as COMPLETED",
                    prospect_id=str(prospect.id),
                    sequence_id=prospect.sequence_id,
                    step=prospect.followup_step,
                )
                with get_session(self.engine) as session:
                    prospect_repo = ProspectRepository(session)
                    prospect_repo.update_status(prospect.id, ProspectStatus.COMPLETED)
                    prospect_repo.update_next_action(prospect.id, None)  # type: ignore[arg-type]
                continue

            template_name = step_config.get("template")
            subject = step_config.get("subject", "")

            if not template_name:
                logger.warning("No template in step config", step=step_config)
                continue

            # Send email
            success, message_id = self.send_email_to_prospect(
                prospect=prospect,
                template_name=template_name,
                subject=subject,
                step=prospect.followup_step,
            )

            if success:
                summary["emails_sent"] += 1
            else:
                summary["emails_failed"] += 1

        # Step 5: Export completed/replied prospects to appropriate sheets
        # This is done in a separate session after all email operations are complete
        if prospects_file:
            logger.info("Exporting completed prospects to Excel")
            try:
                # Get terminal prospects in a fresh session
                with get_session(self.engine) as export_session:
                    export_repo = ProspectRepository(export_session)
                    all_prospects = export_repo.get_all()
                    terminal_prospects = [
                        p
                        for p in all_prospects
                        if p.status
                        in [ProspectStatus.REPLIED.value, ProspectStatus.COMPLETED.value]
                    ]
                # Session is now closed, safe to write to Excel

                if terminal_prospects:
                    export_prospects_to_excel(
                        prospects=terminal_prospects,
                        output_path=prospects_file,
                        preserve_existing=True,
                    )
                    summary["exported"] = {
                        "replied": len(
                            [
                                p
                                for p in terminal_prospects
                                if p.status == ProspectStatus.REPLIED.value
                            ]
                        ),
                        "completed": len(
                            [
                                p
                                for p in terminal_prospects
                                if p.status == ProspectStatus.COMPLETED.value
                            ]
                        ),
                    }
                    logger.info(
                        "Exported prospects to sheets",
                        replied=summary["exported"]["replied"],
                        completed=summary["exported"]["completed"],
                    )
                else:
                    logger.info("No completed/replied prospects to export")
                    summary["exported"] = {"replied": 0, "completed": 0}
            except Exception as e:
                logger.error("Failed to export prospects", error=str(e))
                summary["export_error"] = str(e)

        logger.info("Daily run complete", **summary)
        return summary

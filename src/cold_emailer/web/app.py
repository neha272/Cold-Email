"""Flask web application for cold email campaign management."""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for Python < 3.9
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        ZoneInfo = None

import yaml
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
from sqlalchemy.exc import OperationalError

from cold_emailer.config import EnvSettings, load_config, load_sequences
from cold_emailer.orchestrator import Orchestrator
from cold_emailer.state_store.db import create_database_engine, get_session, init_database
from cold_emailer.state_store.models import ProspectStatus
from cold_emailer.state_store.repo import MessageEventRepository, ProspectRepository
from cold_emailer.utils import get_logger

logger = get_logger(__name__)

# Get workspace root (3 levels up from this file)
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = WORKSPACE_ROOT / "config"
DATA_DIR = WORKSPACE_ROOT / "data"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")
app.config["UPLOAD_FOLDER"] = DATA_DIR
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Load configuration
settings = load_config(CONFIG_DIR / "settings.yaml")
env_settings = EnvSettings()
sequences_data = load_sequences(CONFIG_DIR / "sequences.yaml")
# Keep full structure for orchestrator (it expects {"sequences": {...}})
sequences = sequences_data if isinstance(sequences_data, dict) else {"sequences": {}}
# Extract just sequences dict for templates
sequences_dict = sequences.get("sequences", {}) if isinstance(sequences, dict) else {}
engine = create_database_engine(settings.database.path, echo=settings.database.echo)


def reload_sequences():
    """Reload sequences from file."""
    global sequences, sequences_dict
    sequences_data = load_sequences(CONFIG_DIR / "sequences.yaml")
    # Keep full structure for orchestrator
    sequences = sequences_data if isinstance(sequences_data, dict) else {"sequences": {}}
    # Extract just sequences dict for templates
    sequences_dict = sequences.get("sequences", {}) if isinstance(sequences, dict) else {}
    return sequences


@app.route("/")
def index():
    """Dashboard homepage."""
    try:
        with get_session(engine) as session:
            prospect_repo = ProspectRepository(session)
            event_repo = MessageEventRepository(session)
            
            # Get statistics
            all_prospects = prospect_repo.get_all()
            total_prospects = len(all_prospects)
            
            # Count by status
            status_counts = {}
            for prospect in all_prospects:
                status = prospect.status
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # Get recent events
            recent_events = event_repo.get_all_events(limit=10)
            
            # Get due prospects
            now = datetime.utcnow()
            due_prospects = prospect_repo.get_due_prospects(now, limit=100)
            
            return render_template(
                "index.html",
                total_prospects=total_prospects,
                status_counts=status_counts,
                recent_events=recent_events,
                due_prospects_count=len(due_prospects),
                settings=settings,
            )
    except OperationalError as e:
        error_msg = str(e)
        # Check if it's a "no such table" error
        if "no such table" in error_msg.lower():
            logger.error("Database not initialized", error=error_msg)
            # Determine if running in Docker or locally
            is_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"
            init_cmd = "docker compose exec cold-emailer cold-emailer init-db" if is_docker else "poetry run cold-emailer init-db"
            
            return render_template(
                "error.html",
                error_title="Database Not Initialized",
                error_message="The database has not been initialized. Please run the initialization command first.",
                error_details=error_msg,
                init_command=init_cmd,
            )
        # Re-raise other operational errors
        raise


@app.route("/prospects")
def prospects_list():
    """List all prospects with filtering."""
    status_filter = request.args.get("status")
    search_query = request.args.get("q", "").strip()
    
    with get_session(engine) as session:
        prospect_repo = ProspectRepository(session)
        all_prospects = prospect_repo.get_all()
        
        # Apply filters
        filtered_prospects = all_prospects
        if status_filter:
            filtered_prospects = [p for p in filtered_prospects if p.status == status_filter]
        if search_query:
            search_lower = search_query.lower()
            filtered_prospects = [
                p for p in filtered_prospects
                if (search_lower in p.email.lower() if p.email else False)
                or (search_lower in p.full_name.lower() if p.full_name else False)
                or (search_lower in p.company.lower() if p.company else False)
            ]
        
        return render_template(
            "prospects.html",
            prospects=filtered_prospects,
            status_filter=status_filter,
            search_query=search_query,
            total_count=len(all_prospects),
        )


@app.route("/prospects/add", methods=["GET", "POST"])
def add_prospect():
    """Add a new prospect."""
    if request.method == "POST":
        try:
            with get_session(engine) as session:
                prospect_repo = ProspectRepository(session)
                
                # Get form data
                prospect_data = {
                    "email": request.form.get("email", "").strip(),
                    "full_name": request.form.get("full_name", "").strip(),
                    "company": request.form.get("company", "").strip(),
                    "resume_id": request.form.get("resume_id", "").strip(),
                    "role_title": request.form.get("role_title", "").strip() or None,
                    "sequence_id": request.form.get("sequence_id", "default").strip() or "default",
                    "timezone": request.form.get("timezone", "").strip() or None,
                }
                
                # Validate required fields
                if not prospect_data["email"]:
                    flash("Email is required", "error")
                    return render_template("add_prospect.html", prospect=prospect_data, sequences=sequences_dict)
                if not prospect_data["full_name"]:
                    flash("Full name is required", "error")
                    return render_template("add_prospect.html", prospect=prospect_data, sequences=sequences_dict)
                if not prospect_data["company"]:
                    flash("Company is required", "error")
                    return render_template("add_prospect.html", prospect=prospect_data, sequences=sequences_dict)
                if not prospect_data["resume_id"]:
                    flash("Resume ID is required", "error")
                    return render_template("add_prospect.html", prospect=prospect_data, sequences=sequences_dict)
                
                # Check if prospect already exists
                existing = prospect_repo.get_by_email(prospect_data["email"])
                if existing:
                    flash(f"Prospect with email {prospect_data['email']} already exists", "error")
                    return render_template("add_prospect.html", prospect=prospect_data, sequences=sequences_dict)
                
                # Validate resume file exists
                from cold_emailer.attachments import find_resume_file
                resumes_dir = WORKSPACE_ROOT / settings.paths.resumes_dir
                is_valid, error_msg, resume_info = find_resume_file(prospect_data["resume_id"], resumes_dir)
                if not is_valid:
                    flash(f"Resume file not found: {error_msg or prospect_data['resume_id']}", "error")
                    return render_template("add_prospect.html", prospect=prospect_data, sequences=sequences_dict)
                
                if not resume_info:
                    flash(f"Resume info not found: {prospect_data['resume_id']}", "error")
                    return render_template("add_prospect.html", prospect=prospect_data, sequences=sequences_dict)
                
                prospect_data["resume_path"] = str(resume_info.get("absolute_path"))
                prospect_data["resume_sha256"] = resume_info.get("sha256")
                prospect_data["status"] = ProspectStatus.NEW.value
                prospect_data["followup_step"] = 0
                prospect_data["next_action_at"] = None
                
                # Create prospect
                prospect_repo.create(prospect_data)
                
                flash(f"Prospect {prospect_data['full_name']} added successfully!", "success")
                return redirect(url_for("prospects_list"))
        
        except Exception as e:
            logger.error("Failed to add prospect", error=str(e))
            flash(f"Error adding prospect: {str(e)}", "error")
            return render_template("add_prospect.html", prospect=request.form.to_dict(), sequences=sequences_dict)
    
    # GET request - show form
    return render_template("add_prospect.html", prospect={}, sequences=sequences_dict)


@app.route("/prospects/<prospect_id>/edit", methods=["GET", "POST"])
def edit_prospect(prospect_id):
    """Edit an existing prospect."""
    with get_session(engine) as session:
        prospect_repo = ProspectRepository(session)
        prospect = prospect_repo.get_by_id(prospect_id)
        
        if not prospect:
            flash("Prospect not found", "error")
            return redirect(url_for("prospects_list"))
        
        if request.method == "POST":
            try:
                # Get form data
                prospect_data = {
                    "email": request.form.get("email", "").strip(),
                    "full_name": request.form.get("full_name", "").strip(),
                    "company": request.form.get("company", "").strip(),
                    "resume_id": request.form.get("resume_id", "").strip(),
                    "role_title": request.form.get("role_title", "").strip() or None,
                    "sequence_id": request.form.get("sequence_id", "default").strip() or "default",
                    "timezone": request.form.get("timezone", "").strip() or None,
                }
                
                # Validate required fields
                if not prospect_data["email"]:
                    flash("Email is required", "error")
                    return render_template("edit_prospect.html", prospect=prospect, prospect_data=prospect_data, sequences=sequences_dict)
                if not prospect_data["full_name"]:
                    flash("Full name is required", "error")
                    return render_template("edit_prospect.html", prospect=prospect, prospect_data=prospect_data, sequences=sequences_dict)
                if not prospect_data["company"]:
                    flash("Company is required", "error")
                    return render_template("edit_prospect.html", prospect=prospect, prospect_data=prospect_data, sequences=sequences_dict)
                if not prospect_data["resume_id"]:
                    flash("Resume ID is required", "error")
                    return render_template("edit_prospect.html", prospect=prospect, prospect_data=prospect_data, sequences=sequences_dict)
                
                # Update resume if changed
                if prospect_data["resume_id"] != prospect.resume_id:
                    from cold_emailer.attachments import find_resume_file
                    resumes_dir = WORKSPACE_ROOT / settings.paths.resumes_dir
                    is_valid, resume_path, resume_info = find_resume_file(prospect_data["resume_id"], resumes_dir)
                    if not is_valid:
                        flash(f"Resume file not found: {prospect_data['resume_id']}", "error")
                        return render_template("edit_prospect.html", prospect=prospect, prospect_data=prospect_data, sequences=sequences_dict)
                    prospect_data["resume_path"] = str(resume_path)
                    prospect_data["resume_sha256"] = resume_info.get("sha256") if resume_info else None
                
                # Update prospect (preserve status and followup_step unless explicitly changed)
                prospect.email = prospect_data["email"]
                prospect.full_name = prospect_data["full_name"]
                prospect.company = prospect_data["company"]
                prospect.resume_id = prospect_data["resume_id"]
                prospect.role_title = prospect_data["role_title"]
                prospect.sequence_id = prospect_data["sequence_id"]
                prospect.timezone = prospect_data["timezone"]
                if "resume_path" in prospect_data:
                    prospect.resume_path = prospect_data["resume_path"]
                if "resume_sha256" in prospect_data:
                    prospect.resume_sha256 = prospect_data["resume_sha256"]
                
                flash(f"Prospect {prospect_data['full_name']} updated successfully!", "success")
                return redirect(url_for("prospect_detail", prospect_id=prospect.id))
            
            except Exception as e:
                logger.error("Failed to update prospect", error=str(e))
                flash(f"Error updating prospect: {str(e)}", "error")
                return render_template("edit_prospect.html", prospect=prospect, prospect_data=request.form.to_dict(), sequences=sequences_dict)
        
        # GET request - show form
        return render_template("edit_prospect.html", prospect=prospect, prospect_data={}, sequences=sequences_dict)


@app.route("/prospects/import", methods=["GET", "POST"])
def import_prospects():
    """Import prospects from Excel file."""
    if request.method == "POST":
        try:
            if "file" not in request.files:
                flash("No file provided", "error")
                return redirect(url_for("import_prospects"))
            
            file = request.files["file"]
            if file.filename == "":
                flash("No file selected", "error")
                return redirect(url_for("import_prospects"))
            
            # Save uploaded file temporarily
            filename = secure_filename(file.filename)
            filepath = DATA_DIR / filename
            file.save(str(filepath))
            
            # Import using orchestrator
            orchestrator = Orchestrator(
                settings=settings,
                env_settings=env_settings,
                sequences=sequences,
                dry_run=False,
            )
            
            created, updated, errors = orchestrator.ingest_prospects_file(filepath, reset_state=False)
            
            # Clean up temp file
            if filepath.exists():
                filepath.unlink()
            
            flash(
                f"Import complete! Created: {created}, Updated: {updated}, Errors: {len(errors)}",
                "success" if not errors else "warning",
            )
            
            if errors:
                flash(f"Errors: {', '.join(str(e) for e in errors[:5])}", "error")
            
            return redirect(url_for("prospects_list"))
        
        except Exception as e:
            logger.error("Failed to import prospects", error=str(e))
            flash(f"Error importing prospects: {str(e)}", "error")
            return redirect(url_for("import_prospects"))
    
    # GET request - show upload form
    return render_template("import_prospects.html")


@app.route("/prospects/<prospect_id>")
def prospect_detail(prospect_id):
    """View prospect details and history."""
    with get_session(engine) as session:
        prospect_repo = ProspectRepository(session)
        event_repo = MessageEventRepository(session)
        
        prospect = prospect_repo.get_by_id(prospect_id)
        if not prospect:
            flash("Prospect not found", "error")
            return redirect(url_for("prospects_list"))
        
        events = event_repo.get_by_prospect_id(prospect.id, limit=50)
        
        return render_template(
            "prospect_detail.html",
            prospect=prospect,
            events=events,
        )


@app.route("/campaign/run", methods=["POST"])
def run_campaign():
    """Run email campaign."""
    dry_run = request.form.get("dry_run") == "true"
    prospects_file = DATA_DIR / "prospects.xlsx"
    
    try:
        orchestrator = Orchestrator(
            settings=settings,
            env_settings=env_settings,
            sequences=sequences,
            dry_run=dry_run,
        )
        
        summary = orchestrator.run_daily(prospects_file=prospects_file)
        
        flash(
            f"Campaign completed! Sent: {summary['emails_sent']}, Failed: {summary['emails_failed']}, Replies: {summary['replies_detected']}",
            "success",
        )
        
        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        logger.error("Failed to run campaign", error=str(e))
        flash(f"Campaign failed: {str(e)}", "error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/campaign/check-replies", methods=["POST"])
def check_replies():
    """Manually check for replies."""
    try:
        orchestrator = Orchestrator(
            settings=settings,
            env_settings=env_settings,
            sequences=sequences,
            dry_run=False,
        )
        
        replies_detected = orchestrator.detect_replies()
        
        flash(f"Found {replies_detected} new replies", "success")
        return jsonify({"success": True, "replies_detected": replies_detected})
    except Exception as e:
        logger.error("Failed to check replies", error=str(e))
        flash(f"Failed to check replies: {str(e)}", "error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/stats")
def stats():
    """Statistics and visualizations."""
    with get_session(engine) as session:
        prospect_repo = ProspectRepository(session)
        event_repo = MessageEventRepository(session)
        
        all_prospects = prospect_repo.get_all()
        all_events = event_repo.get_all_events(limit=1000)
        
        # Status distribution
        status_counts = {}
        for prospect in all_prospects:
            status = prospect.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Event timeline (last 30 days)
        from collections import defaultdict
        events_by_date = defaultdict(int)
        for event in all_events:
            if event.occurred_at:
                date_key = event.occurred_at.strftime("%Y-%m-%d")
                events_by_date[date_key] += 1
        
        # Conversion rates
        total = len(all_prospects)
        replied = status_counts.get(ProspectStatus.REPLIED.value, 0)
        completed = status_counts.get(ProspectStatus.COMPLETED.value, 0)
        
        response_rate = (replied / total * 100) if total > 0 else 0
        
        return render_template(
            "stats.html",
            status_counts=status_counts,
            events_by_date=dict(events_by_date),
            total_prospects=total,
            response_rate=response_rate,
            replied_count=replied,
            completed_count=completed,
        )


@app.route("/settings")
def settings_page():
    """View and edit settings."""
    return render_template(
        "settings.html",
        settings=settings,
        env_settings=env_settings,
        sequences=sequences_dict,
    )


@app.route("/sequences")
def sequences_list():
    """List all email sequences."""
    return render_template(
        "sequences.html",
        sequences=sequences_dict,
    )


@app.route("/sequences/<sequence_id>")
def sequence_detail(sequence_id):
    """View and edit a specific sequence."""
    if sequence_id not in sequences_dict:
        flash("Sequence not found", "error")
        return redirect(url_for("sequences_list"))
    
    sequence = sequences_dict[sequence_id]
    sequence["id"] = sequence_id
    
    # Get available templates
    templates_dir = WORKSPACE_ROOT / settings.paths.templates_dir
    available_templates = []
    if templates_dir.exists():
        for template_file in templates_dir.glob("*.md"):
            available_templates.append(template_file.stem)
    
    return render_template(
        "sequence_detail.html",
        sequence=sequence,
        sequence_id=sequence_id,
        available_templates=available_templates,
    )


@app.route("/sequences/add", methods=["GET", "POST"])
def add_sequence():
    """Add a new email sequence."""
    templates_dir = WORKSPACE_ROOT / settings.paths.templates_dir
    available_templates = []
    if templates_dir.exists():
        for template_file in templates_dir.glob("*.md"):
            available_templates.append(template_file.stem)
    
    if request.method == "POST":
        try:
            sequence_id = request.form.get("sequence_id", "").strip().lower().replace(" ", "_")
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            
            if not sequence_id:
                flash("Sequence ID is required", "error")
                return render_template("add_sequence.html", available_templates=available_templates)
            if not name:
                flash("Sequence name is required", "error")
                return render_template("add_sequence.html", available_templates=available_templates)
            if sequence_id in sequences:
                flash(f"Sequence ID '{sequence_id}' already exists", "error")
                return render_template("add_sequence.html", available_templates=available_templates)
            
            # Parse steps from form
            steps = []
            step_count = int(request.form.get("step_count", 0))
            
            for i in range(step_count):
                step_num = request.form.get(f"step_{i}_num", "")
                template = request.form.get(f"step_{i}_template", "")
                wait_days = request.form.get(f"step_{i}_wait_days", "0")
                subject = request.form.get(f"step_{i}_subject", "")
                
                if step_num and template:
                    try:
                        steps.append({
                            "step": int(step_num),
                            "template": template,
                            "wait_days": int(wait_days) if wait_days else 0,
                            "subject": subject,
                        })
                    except ValueError:
                        continue
            
            if not steps:
                flash("At least one step is required", "error")
                return render_template("add_sequence.html", available_templates=available_templates)
            
            # Load existing sequences
            sequences_path = CONFIG_DIR / "sequences.yaml"
            with open(sequences_path, "r") as f:
                sequences_data = yaml.safe_load(f) or {}
            
            # Add new sequence
            sequences_data.setdefault("sequences", {})[sequence_id] = {
                "name": name,
                "description": description,
                "steps": sorted(steps, key=lambda x: x["step"]),
            }
            
            # Save to file
            with open(sequences_path, "w") as f:
                yaml.dump(sequences_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            
            # Reload sequences
            reload_sequences()
            
            flash(f"Sequence '{name}' added successfully!", "success")
            return redirect(url_for("sequences_list"))
        
        except Exception as e:
            logger.error("Failed to add sequence", error=str(e))
            flash(f"Error adding sequence: {str(e)}", "error")
            return render_template("add_sequence.html", available_templates=available_templates)
    
    return render_template("add_sequence.html", available_templates=available_templates)


@app.route("/sequences/<sequence_id>/edit", methods=["GET", "POST"])
def edit_sequence(sequence_id):
    """Edit an existing email sequence."""
    if sequence_id not in sequences_dict:
        flash("Sequence not found", "error")
        return redirect(url_for("sequences_list"))
    
    templates_dir = WORKSPACE_ROOT / settings.paths.templates_dir
    available_templates = []
    if templates_dir.exists():
        for template_file in templates_dir.glob("*.md"):
            available_templates.append(template_file.stem)
    
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            
            if not name:
                flash("Sequence name is required", "error")
                return redirect(url_for("edit_sequence", sequence_id=sequence_id))
            
            # Parse steps from form
            steps = []
            step_count = int(request.form.get("step_count", 0))
            
            for i in range(step_count):
                step_num = request.form.get(f"step_{i}_num", "")
                template = request.form.get(f"step_{i}_template", "")
                wait_days = request.form.get(f"step_{i}_wait_days", "0")
                subject = request.form.get(f"step_{i}_subject", "")
                
                if step_num and template:
                    try:
                        steps.append({
                            "step": int(step_num),
                            "template": template,
                            "wait_days": int(wait_days) if wait_days else 0,
                            "subject": subject,
                        })
                    except ValueError:
                        continue
            
            if not steps:
                flash("At least one step is required", "error")
                return redirect(url_for("edit_sequence", sequence_id=sequence_id))
            
            # Load existing sequences
            sequences_path = CONFIG_DIR / "sequences.yaml"
            import yaml
            with open(sequences_path, "r") as f:
                sequences_data = yaml.safe_load(f) or {}
            
            # Update sequence
            sequences_data.setdefault("sequences", {})[sequence_id] = {
                "name": name,
                "description": description,
                "steps": sorted(steps, key=lambda x: x["step"]),
            }
            
            # Save to file
            with open(sequences_path, "w") as f:
                yaml.dump(sequences_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            
            # Reload sequences
            reload_sequences()
            
            flash(f"Sequence '{name}' updated successfully!", "success")
            return redirect(url_for("sequences_list"))
        
        except Exception as e:
            logger.error("Failed to update sequence", error=str(e))
            flash(f"Error updating sequence: {str(e)}", "error")
            return redirect(url_for("edit_sequence", sequence_id=sequence_id))
    
    sequence = sequences_dict[sequence_id]
    sequence["id"] = sequence_id
    return render_template(
        "edit_sequence.html",
        sequence=sequence,
        sequence_id=sequence_id,
        available_templates=available_templates,
    )


@app.template_filter("datetime")
def format_datetime(value):
    """Format datetime for display in Chicago timezone."""
    if value is None:
        return "N/A"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except Exception:
            return value
    
    # Get Chicago timezone (UTC-6 or UTC-5 depending on DST)
    if ZoneInfo:
        chicago_tz = ZoneInfo("America/Chicago")
    else:
        # Fallback: Use fixed UTC-6 offset (CST)
        chicago_tz = timezone(timedelta(hours=-6))
    
    # Assume UTC if datetime is naive, otherwise use its timezone
    if value.tzinfo is None:
        # Naive datetime - assume it's UTC
        if ZoneInfo:
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        else:
            value = value.replace(tzinfo=timezone.utc)
    
    # Convert to Chicago timezone
    local_time = value.astimezone(chicago_tz)
    
    return local_time.strftime("%Y-%m-%d %H:%M:%S %Z")


@app.template_filter("timesince")
def time_since(value):
    """Human-readable time since in Chicago timezone."""
    if value is None:
        return "Never"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except Exception:
            return value
    
    # Get Chicago timezone
    if ZoneInfo:
        chicago_tz = ZoneInfo("America/Chicago")
        utc_tz = ZoneInfo("UTC")
    else:
        # Fallback: Use fixed UTC-6 offset (CST)
        chicago_tz = timezone(timedelta(hours=-6))
        utc_tz = timezone.utc
    
    # Assume UTC if datetime is naive, otherwise use its timezone
    if value.tzinfo is None:
        # Naive datetime - assume it's UTC
        value = value.replace(tzinfo=utc_tz)
    
    # Convert to Chicago timezone for comparison
    local_value = value.astimezone(chicago_tz)
    now = datetime.now(chicago_tz)
    
    diff = now - local_value
    
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "Just now"


def main():
    """Run the Flask development server."""
    # Get port from environment or default to 5000
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    
    print("\n" + "="*60)
    print("🚀 Cold Email Campaign Manager - Web Interface")
    print("="*60)
    print(f"\n📍 Server running at: http://0.0.0.0:{port}")
    print(f"📁 Workspace: {WORKSPACE_ROOT}")
    print(f"🗄️  Database: {settings.database.path}")
    print("\n💡 Press Ctrl+C to stop the server\n")
    
    app.run(debug=debug, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

# Quick Setup Guide

## ✅ Your Gmail credentials have been configured in `.env`

## 📧 Where to Add Emails (Prospects)

**File:** `data/prospects.xlsx` (or CSV)

Edit this file with your prospect information. Required columns:
- `email` - Recipient's email address
- `full_name` - Recipient's full name
- `company` - Company name
- `resume_id` - Which resume to attach (must match a resume_id in resume_manifest.csv)

Optional columns:
- `prospect_id` - Auto-generated if not provided
- `role_title` - Job title
- `sequence_id` - Which follow-up sequence to use (default, aggressive, or gentle)
- `timezone` - Timezone
- `variables_json` - Custom template variables as JSON

### Example:
```csv
email,full_name,company,resume_id,role_title,sequence_id
john@example.com,John Doe,Acme Corp,RES-001,Software Engineer,default
jane@example.com,Jane Smith,Tech Corp,RES-001,Product Manager,aggressive
```

## 📎 Where to Add Resumes

**Directory:** `assets/resumes/`

1. Place your PDF resume files in this directory
2. Name them with a unique identifier (e.g., `RES-001.pdf`, `RES-002.pdf`)

**File:** `data/resume_manifest.xlsx` (or CSV)

Add an entry for each resume file. The `sha256` will be computed automatically if left blank.

### Example:
```csv
resume_id,relative_path,sha256,version
RES-001,assets/resumes/RES-001.pdf,,1.0
RES-002,assets/resumes/RES-002.pdf,,1.0
```

**Important:** 
- The `resume_id` in `resume_manifest.xlsx` must match the `resume_id` in `prospects.xlsx`
- The `relative_path` should be relative to the project root

## ⏰ How to Configure Follow-ups and Intervals

**File:** `config/sequences.yaml`

This file controls:
- **Number of follow-ups**: Add more steps to the `steps` array
- **Interval between follow-ups**: Change the `wait_days` value for each step

### Current Sequences:

1. **default** - 3 follow-ups (initial + 2 follow-ups)
   - Initial email
   - Follow-up 1 after 3 days
   - Follow-up 2 after 5 more days (8 days total)

2. **aggressive** - Faster follow-ups
   - Initial email
   - Follow-up 1 after 2 days
   - Follow-up 2 after 3 more days (5 days total)

3. **gentle** - Slower follow-ups
   - Initial email
   - Follow-up 1 after 5 days
   - Follow-up 2 after 7 more days (12 days total)

### To Modify Follow-up Intervals:

Edit the `wait_days` value in `config/sequences.yaml`:

```yaml
sequences:
  default:
    steps:
      - step: 0
        template: "initial"
        wait_days: 3    # ← Change this to wait 3 days before first follow-up
        subject: "Quick question about {{ company }}"
      - step: 1
        template: "followup_1"
        wait_days: 5    # ← Change this to wait 5 days before second follow-up
        subject: "Following up on my message"
      - step: 2
        template: "followup_2"
        wait_days: 7    # ← Change this to wait 7 days before third follow-up
        subject: "Last follow-up"
```

### To Add More Follow-ups:

Add more steps to the sequence:

```yaml
sequences:
  default:
    steps:
      - step: 0
        template: "initial"
        wait_days: 3
        subject: "Quick question about {{ company }}"
      - step: 1
        template: "followup_1"
        wait_days: 5
        subject: "Following up on my message"
      - step: 2
        template: "followup_2"
        wait_days: 7
        subject: "Last follow-up"
      - step: 3                    # ← Add this for a 4th follow-up
        template: "followup_1"     # ← Reuse a template or create new one
        wait_days: 10              # ← Wait 10 more days
        subject: "Final follow-up"
```

**Note:** You'll need to create corresponding template files in `templates/` if you add new templates.

## 🚀 Quick Start Workflow

1. **Add your resumes:**
   - Put PDF files in `assets/resumes/`
   - Add entries to `data/resume_manifest.xlsx`

2. **Add your prospects:**
   - Edit `data/prospects.xlsx` with recipient information
   - Make sure `resume_id` matches an entry in the manifest

3. **Configure follow-ups (optional):**
   - Edit `config/sequences.yaml` to adjust intervals
   - Choose sequence in `prospects.xlsx` (`sequence_id` column)

4. **Test with dry-run:**
   ```bash
   poetry run cold-emailer run --file data/prospects.xlsx --dry-run
   ```

5. **Run live:**
   ```bash
   poetry run cold-emailer run --file data/prospects.xlsx --confirm-send
   ```

## 📝 Summary

- **Emails/Prospects:** `data/prospects.xlsx` (or CSV)
- **Resumes:** `assets/resumes/` directory + `data/resume_manifest.xlsx` (or CSV)
- **Follow-up intervals:** `config/sequences.yaml` (edit `wait_days`)
- **Number of follow-ups:** `config/sequences.yaml` (add more `steps`)

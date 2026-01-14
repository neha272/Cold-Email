# How to Run Cold Emailer - Quick Reference

## ✅ Current Status

Your tool is **working correctly**! The only thing missing is the resume PDF files.

## 🚀 Quick Commands

### Test Run (No Emails Sent)
```bash
poetry run cold-emailer run data/prospects.xlsx --dry-run
```

### Live Run (Sends Real Emails)
```bash
poetry run cold-emailer run data/prospects.xlsx --confirm-send
```

## 📋 Before Running

### 1. Add Resume PDF Files

Place your PDF files in `assets/resumes/`:
```bash
# Example:
assets/resumes/RES-00042.pdf
assets/resumes/RES-00043.pdf
```

The filenames must match the `resume_id` in your `data/resume_manifest.xlsx`.

### 2. Update Your Data Files

- **`data/prospects.xlsx`** - Add your real prospect emails
- **`data/resume_manifest.xlsx`** - Ensure paths point to your PDF files

### 3. Adjust Send Window (Optional)

If you see "Outside send window", edit `config/settings.yaml`:
```yaml
throttling:
  send_window_start: "00:00"  # All day
  send_window_end: "23:59"
```

## 📊 What Each Command Does

### `--dry-run`
- ✅ Validates files
- ✅ Shows what would be sent
- ❌ **Does NOT send emails**
- ✅ Safe to run anytime

### `--confirm-send` (without `--dry-run`)
- ✅ Actually sends emails
- ⚠️ **Sends real emails to real people**
- ⚠️ Use only after testing with `--dry-run`

## 🎯 Typical Workflow

1. **Add resume PDFs** → `assets/resumes/`
2. **Update prospects** → `data/prospects.xlsx`
3. **Test** → `poetry run cold-emailer run data/prospects.xlsx --dry-run`
4. **Review output** → Check for errors
5. **Run live** → `poetry run cold-emailer run data/prospects.xlsx --confirm-send`

## ⚠️ Important Notes

- **Resume files are required** - The tool won't send without valid resume PDFs
- **Send window** - Default is 9am-5pm (adjustable in config)
- **Dry-run is safe** - Always test with `--dry-run` first
- **Gmail configured** - Your credentials are already set up in `.env`

## 🔍 Check Status

```bash
# See prospect status
poetry run cold-emailer status

# Export events log
poetry run cold-emailer export-events
```

## 📝 Current Issues (From Your Last Run)

1. ✅ **Fixed**: Command syntax working
2. ✅ **Fixed**: Excel files loading
3. ⚠️ **Action needed**: Add resume PDF files to `assets/resumes/`
4. ⚠️ **Optional**: Adjust send window if outside 9am-5pm

Once you add the resume PDF files, everything will work!

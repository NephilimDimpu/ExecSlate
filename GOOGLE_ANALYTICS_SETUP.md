# Google Analytics Setup for ExecSlate

## Step 1: Get Your Measurement ID

1. Go to https://analytics.google.com
2. Click "Start measuring" (or "Admin" gear icon)
3. Create a new property:
   - Account name: **ExecSlate**
   - Property name: **ExecSlate Web**
   - Time zone: Your timezone
   - Select **"Web"**
   - Website URL: `http://localhost:8000` (change to your domain when deployed)
4. Copy your **Measurement ID** (looks like `G-XXXXXXXXXX`)

---

## Step 2: Add This Code to ALL Your HTML Templates

**Add this right after `<head>` in every template:**

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- Google Analytics -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-XXXXXXXXXX');
    </script>
    
    <!-- Meta Tags for SEO -->
    <meta name="description" content="Turn revenue data into board-ready executive reports. AI-powered insights, charts, and PowerPoint exports for consultants. Free plan available.">
    <meta property="og:title" content="ExecSlate — Executive Intelligence From Raw Data">
    <meta property="og:description" content="Generate consulting-grade revenue reports from CSV files in seconds.">
    <meta property="og:image" content="/static/og-image.png">
    <meta property="og:url" content="https://execslate.com">
    <meta name="twitter:card" content="summary_large_image">
    
    <!-- Rest of your head content -->
    <title>ExecSlate</title>
    ...
</head>
```

**Replace `G-XXXXXXXXXX` with your actual Measurement ID (twice!)**

---

## Step 3: Add to These Files

Add the GA + Meta code to EVERY template:

- [ ] `landing.html`
- [ ] `dashboard.html`
- [ ] `report.html`
- [ ] `pricing.html`
- [ ] `login.html`
- [ ] `admin.html`
- [ ] `error.html`

---

## Step 4: Test It Works

1. Run your app: `uvicorn app:app --reload`
2. Visit `http://localhost:8000`
3. Go to Google Analytics → Reports → Realtime
4. You should see **1 active user** (you!)

✅ Done!

---

## ⚠️ Don't Worry About:

- ❌ GA4 migration (you're starting fresh, no migration needed)
- ❌ Google Search Console (do this after you have 100 visitors)
- ❌ SEO ranking (doesn't matter until you have traffic)
- ❌ Documentation transfers (irrelevant for you)

**Just copy-paste the code above. That's it.**

---

## When to Update:

**Before deploying to production:**
- Change `http://localhost:8000` → your actual domain
- Update `og:url` to your real URL

That's all. Don't overthink it.

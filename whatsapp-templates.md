# WhatsApp Templates — copy-paste sheet for Gupshup

7 templates × 4 languages = **28 submissions**.
Language codes: `en` English · `hi` Hindi · `mr` Marathi · `bn` Bengali

## How to submit each one

Gupshup → **Templates** → **Create Template**

| Field | What to enter |
|---|---|
| Template name | exactly as written below, lowercase with underscores |
| Category | Utility |
| Language | en, then repeat for hi, mr, bn |
| Template type | Text |
| Body | copy the block below |
| Template Labels | required by Gupshup. `Support request update` for 1–2, `Support ticket update` for 3–7 |
| Footer | the footer line below, or none where it says none |
| Buttons | Quick Reply, labels below |
| Sample values | required for every `{{1}}` — use the examples below |

Type `{{1}}` yourself and Gupshup's editor mangles it into `{{{1}}1}}`. Use the
**Add variable** button under the body box instead — it inserts the next number and
adds a sample-value row underneath. The cursor stays in the body afterwards, so you
can keep typing straight after the variable.

**Use the same template name for all four languages.** Only the language and the text change.

**Submit English first, alone. Wait for the result.** English decides the category for
the whole name. Only once it comes back approved as Utility do you submit hi, mr and bn.

## Rules that cause rejection

- **All four languages of a name must share one category.** You pick Utility, but Meta's
  classifier decides. If English lands in Marketing, every hi/mr/bn submitted as Utility
  is rejected against it. This is what killed the first attempt.
- **Greetings and welcomes read as Marketing.** "Hello", "Welcome", "We're here to help",
  a brand name, 🙏 or 👋 near the top — all push the classifier towards Marketing. Utility
  means the message answers something the contact themselves asked for. The bodies below
  are written plainly for that reason.
- **A deleted name is blocked for 30 days.** You cannot resubmit under a name you deleted
  until the block expires, which is why template 1 is renamed.
- **No emoji in any body below.** Emoji are allowed and do not decide the category on
  their own — templates 5–7 are plainly transactional and would pass with them. They are
  gone because the first attempt was rejected, and after a rejection the safest possible
  version goes in. Add them back by editing an approved template if you want them.
- Button text longer than **20 characters** — the labels below are all within the limit
- No emoji in button labels
- A body that starts or ends with a variable
- Fake sample values like "test123"

## Which of these actually need approval

Templates **1–4** are only ever sent as a reply to an inbound message, inside the 24-hour
customer service window. Inside that window a free-form interactive message works instead
— no Meta review, no per-message cost. Templates **5–7** genuinely need approval, because
an agent may update or resolve a ticket days after the contact last wrote.

If you take the free-form route for 1–4, this sheet drops from 28 submissions to 12.

---

# Template 1 — support_language_selection

> **Renamed.** `welcome_language_select` was auto-classified MARKETING by Meta, so the
> hi/mr/bn versions could never pass as Utility. All four were deleted, and that name is
> blocked for 30 days. The body below carries no greeting, no emoji and no footer — it
> states that a request arrived and asks one question, which is what Utility means.

Buttons (same in all four languages): `English` · `हिन्दी` · `Regional`
Variables: none
Footer: none — leave the field empty

### en
```
Your support request has been received.

Select the language you want to continue in.
```

### hi
```
आपका सपोर्ट अनुरोध प्राप्त हो गया है।

आप किस भाषा में आगे बढ़ना चाहते हैं, चुनें।
```

### mr
```
तुमची सपोर्ट विनंती मिळाली आहे.

तुम्हाला कोणत्या भाषेत पुढे जायचे आहे ते निवडा.
```

### bn
```
আপনার সাপোর্ট অনুরোধ পাওয়া গেছে।

আপনি কোন ভাষায় এগিয়ে যেতে চান তা নির্বাচন করুন।
```

---

# Template 2 — new_user_issue_category

Variables: none

> Same treatment as template 1: the original body opened with "We're here to help! 🛠",
> which reads as Marketing. Rewritten to reference the contact's own request.

### en
```
Your request has been logged.

Select the category of the issue you are facing:
```
Footer: `Select the category that best matches your issue`
Buttons: `Device` · `Software` · `Other`

### hi
```
आपका अनुरोध दर्ज कर लिया गया है।

अपनी समस्या की श्रेणी चुनें:
```
Footer: `अपनी समस्या से मिलती-जुलती श्रेणी चुनें`
Buttons: `डिवाइस` · `सॉफ़्टवेयर` · `अन्य`

### mr
```
तुमची विनंती नोंदवली गेली आहे.

तुमच्या समस्येची श्रेणी निवडा:
```
Footer: `तुमच्या समस्येशी जुळणारी श्रेणी निवडा`
Buttons: `डिव्हाइस` · `सॉफ्टवेअर` · `इतर`

### bn
```
আপনার অনুরোধ নথিভুক্ত হয়েছে।

আপনার সমস্যার বিভাগ নির্বাচন করুন:
```
Footer: `আপনার সমস্যার সাথে মিলে এমন বিভাগ বেছে নিন`
Buttons: `ডিভাইস` · `সফটওয়্যার` · `অন্যান্য`

> The PDF's longer labels ("Device / Hardware", "डिवाइस / हार्डवेयर") run past 20 characters in Indian scripts, so these short ones are used instead.

---

# Template 3 — returning_user_options

Variables: `{{1}}` = existing ticket ID — sample: `TKT-20260916-0042`

> "Welcome back! 👋" removed for the same reason as template 1. The brackets around the
> ticket ID are gone too — the Add variable button drops `{{1}}` in on its own and the
> sentence reads fine without them.

### en
```
You have an existing support ticket {{1}} that is still in progress.

What would you like to do?
```
Footer: `Tap a button to continue`
Buttons: `New Ticket` · `Previous Ticket`

### hi
```
आपका एक मौजूदा सपोर्ट टिकट {{1}} अभी भी प्रगति पर है।

आप क्या करना चाहेंगे?
```
Footer: `जारी रखने के लिए बटन दबाएं`
Buttons: `नया टिकट` · `पिछला टिकट`

### mr
```
तुमचे एक सपोर्ट तिकीट {{1}} अजूनही सुरू आहे.

तुम्हाला काय करायचे आहे?
```
Footer: `पुढे जाण्यासाठी बटण दाबा`
Buttons: `नवीन तिकीट` · `मागील तिकीट`

### bn
```
আপনার একটি সাপোর্ট টিকিট {{1}} এখনও চলছে।

আপনি কী করতে চান?
```
Footer: `চালিয়ে যেতে বোতামে চাপ দিন`
Buttons: `নতুন টিকিট` · `আগের টিকিট`

> "Check Previous Ticket" is 21 characters, one over the limit, so it is shortened to "Previous Ticket".

---

# Template 4 — upload_media_request

Variables: `{{1}}` = selected category — sample: `Software`

### en
```
Thank you for selecting {{1}}.

Please upload a photo or video showing the issue you are facing.

You can share it directly in this chat.
```
Footer: `This helps our team resolve your issue faster`
Buttons: `Upload Now` · `Skip`

### hi
```
आपने {{1}} चुना है, धन्यवाद।

कृपया अपनी समस्या दिखाने वाली एक फ़ोटो या वीडियो अपलोड करें।

आप इसे सीधे इस चैट में भेज सकते हैं।
```
Footer: `इससे हमारी टीम आपकी समस्या जल्दी हल कर पाएगी`
Buttons: `अभी अपलोड करें` · `छोड़ें`

### mr
```
तुम्ही {{1}} निवडले, धन्यवाद.

कृपया तुमची समस्या दाखवणारा फोटो किंवा व्हिडिओ पाठवा.

तुम्ही तो थेट या चॅटमध्ये पाठवू शकता.
```
Footer: `यामुळे आमची टीम तुमची समस्या लवकर सोडवू शकेल`
Buttons: `आता पाठवा` · `वगळा`

### bn
```
আপনি {{1}} নির্বাচন করেছেন, ধন্যবাদ।

অনুগ্রহ করে আপনার সমস্যার একটি ছবি বা ভিডিও পাঠান।

আপনি এটি সরাসরি এই চ্যাটে পাঠাতে পারেন।
```
Footer: `এতে আমাদের টিম দ্রুত সমাধান করতে পারবে`
Buttons: `এখনই পাঠান` · `বাদ দিন`

---

# Template 5 — ticket_status_update

Buttons: none
Variables — samples:
`{{1}}` `TKT-20260916-0042` · `{{2}}` `Software` · `{{3}}` `In Progress` · `{{4}}` `16 Sep 2026`

### en
```
Here is the status of your support ticket:

Ticket ID: {{1}}
Category: {{2}}
Status: {{3}}
Raised on: {{4}}

Our team is actively working on it. We will notify you as soon as it is resolved.
```
Footer: `Thank you for your patience`

### hi
```
आपके सपोर्ट टिकट की स्थिति:

टिकट ID: {{1}}
श्रेणी: {{2}}
स्थिति: {{3}}
दर्ज दिनांक: {{4}}

हमारी टीम इस पर सक्रिय रूप से काम कर रही है। समाधान होते ही हम आपको सूचित करेंगे।
```
Footer: `आपके धैर्य के लिए धन्यवाद`

### mr
```
तुमच्या सपोर्ट तिकिटाची स्थिती:

तिकीट ID: {{1}}
श्रेणी: {{2}}
स्थिती: {{3}}
नोंद दिनांक: {{4}}

आमची टीम यावर काम करत आहे. समस्या सुटताच आम्ही तुम्हाला कळवू.
```
Footer: `तुमच्या संयमाबद्दल धन्यवाद`

### bn
```
আপনার সাপোর্ট টিকিটের অবস্থা:

টিকিট ID: {{1}}
বিভাগ: {{2}}
অবস্থা: {{3}}
জমা তারিখ: {{4}}

আমাদের টিম এটি নিয়ে কাজ করছে। সমাধান হলেই আপনাকে জানানো হবে।
```
Footer: `আপনার ধৈর্যের জন্য ধন্যবাদ`

---

# Template 6 — ticket_created_confirmation

Buttons: none
Variables — samples:
`{{1}}` `TKT-20260916-0058` · `{{2}}` `Device` · `{{3}}` `+91 98765 43210`

### en
```
Your complaint has been logged successfully.

Ticket ID: {{1}}
Category: {{2}}
WhatsApp: {{3}}

Our support team has been notified and is looking into your issue. Expected resolution time is 48 hours.
```
Footer: `We will message you here once it is resolved`

### hi
```
आपकी शिकायत सफलतापूर्वक दर्ज कर ली गई है।

टिकट ID: {{1}}
श्रेणी: {{2}}
व्हाट्सएप: {{3}}

हमारी सपोर्ट टीम को सूचित कर दिया गया है और वे आपकी समस्या पर काम कर रहे हैं। समाधान का अनुमानित समय 48 घंटे है।
```
Footer: `समस्या हल होते ही हम यहीं सूचित करेंगे`

### mr
```
तुमची तक्रार यशस्वीरित्या नोंदवली गेली आहे.

तिकीट ID: {{1}}
श्रेणी: {{2}}
व्हॉट्सॲप: {{3}}

आमच्या सपोर्ट टीमला कळवण्यात आले आहे आणि ते तुमच्या समस्येवर काम करत आहेत. अपेक्षित वेळ 48 तास आहे.
```
Footer: `समस्या सुटल्यावर आम्ही येथेच कळवू`

### bn
```
আপনার অভিযোগ সফলভাবে নথিভুক্ত হয়েছে।

টিকিট ID: {{1}}
বিভাগ: {{2}}
হোয়াটসঅ্যাপ: {{3}}

আমাদের সাপোর্ট টিমকে জানানো হয়েছে এবং তারা আপনার সমস্যাটি দেখছে। সমাধানের সম্ভাব্য সময় 48 ঘণ্টা।
```
Footer: `সমাধান হলে আমরা এখানেই জানাব`

---

# Template 7 — ticket_resolved

Buttons: none
Variables — samples:
`{{1}}` `TKT-20260916-0058` · `{{2}}` `The VR headset app has been updated. Please restart and try again.`

> The greeting went here too, and the quotes around Hi are gone — a quoted word inside a
> body is one more thing for a reviewer to trip over, and the sentence works without them.

### en
```
Your support ticket has been resolved.

Ticket ID: {{1}}
Resolution: {{2}}

If you still face any issues, send us Hi again and we will help you right away.
```
Footer: `Thank you for your patience`

### hi
```
आपके सपोर्ट टिकट का समाधान हो गया है।

टिकट ID: {{1}}
समाधान: {{2}}

अगर आपको अभी भी कोई समस्या है, तो हमें फिर से Hi भेजें और हम तुरंत आपकी मदद करेंगे।
```
Footer: `आपके धैर्य के लिए धन्यवाद`

### mr
```
तुमच्या सपोर्ट तिकिटाचे निराकरण झाले आहे.

तिकीट ID: {{1}}
समाधान: {{2}}

तरीही काही अडचण असल्यास, आम्हाला पुन्हा Hi पाठवा, आम्ही लगेच मदत करू.
```
Footer: `तुमच्या संयमाबद्दल धन्यवाद`

### bn
```
আপনার সাপোর্ট টিকিটের সমাধান হয়েছে।

টিকিট ID: {{1}}
সমাধান: {{2}}

এখনও সমস্যা থাকলে আবার Hi পাঠান, আমরা সঙ্গে সঙ্গে সাহায্য করব।
```
Footer: `আপনার ধৈর্যের জন্য ধন্যবাদ`

---

# Checklist

All seven English versions were submitted on **16 Sept 2026** as Utility.

| # | Template | Needed? | en | hi | mr | bn |
|---|---|---|---|---|---|---|
| 1 | support_language_selection | in-session | ☑ approved, Utility | ☐ | ☐ | ☐ |
| 2 | new_user_issue_category | in-session | ☑ submitted | ☐ | ☐ | ☐ |
| 3 | returning_user_options | in-session | ☑ approved, Utility | ☐ | ☐ | ☐ |
| 4 | upload_media_request | in-session | ☑ submitted | ☐ | ☐ | ☐ |
| 5 | ticket_status_update | **required** | ☑ submitted | ☐ | ☐ | ☐ |
| 6 | ticket_created_confirmation | **required** | ☑ submitted | ☐ | ☐ | ☐ |
| 7 | ticket_resolved | **required** | ☑ submitted | ☐ | ☐ | ☐ |

"in-session" means the bot only ever sends it as a reply, so a free-form interactive
message would do the same job without approval. See "Which of these actually need
approval" above.

Approval takes 24–48 hours. Status shows Pending, then Approved or Rejected.

Do English first and on its own. Tick a language box only once it shows **Approved** and
the category reads **Utility** — an approval in the Marketing category is still a problem,
because it locks the other three languages to Marketing too.

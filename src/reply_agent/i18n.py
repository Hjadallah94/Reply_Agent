"""Owner-facing dashboard UI translations (Doc 3 Phase 6.6, scoped slice — Arabic/English + RTL
on the existing server-rendered dashboard). Only affects dashboard chrome: labels, headings,
buttons, badges. Never the agent's actual customer-facing replies, which already correctly mix
Arabic/English based on the customer's own message (generate_response.py, untouched by this).

Arabic strings here are standard/formal Arabic for UI chrome — deliberately distinct from the
dialectal Arabic the agent uses in real customer replies (brand_voice samples), which is a
different register for a different audience.
"""

from fastapi import Request

SUPPORTED_LANGUAGES = ("en", "ar")
DEFAULT_LANGUAGE = "en"

TRANSLATIONS: dict[str, dict[str, str]] = {
    # --- base.html ---
    "base.logout": {"en": "Log out", "ar": "تسجيل الخروج"},
    "base.enable_notifications": {"en": "Enable notifications", "ar": "تفعيل الإشعارات"},
    # Theme toggle (Doc 3 roadmap, dashboard redesign) — label always shows the CURRENT state,
    # clicking advances to the next one in theming.py's THEME_OPTIONS cycle.
    "base.theme_system": {"en": "Auto", "ar": "تلقائي"},
    "base.theme_light": {"en": "Light", "ar": "فاتح"},
    "base.theme_dark": {"en": "Dark", "ar": "داكن"},
    # --- dashboard.html ---
    "dashboard.back_all_businesses": {"en": "All businesses", "ar": "جميع الأعمال"},
    "dashboard.whatsapp_connected": {"en": "WhatsApp connected", "ar": "واتساب متصل"},
    "dashboard.connect_whatsapp": {"en": "Connect WhatsApp", "ar": "ربط واتساب"},
    "dashboard.messenger_connected": {"en": "Messenger connected", "ar": "ماسنجر متصل"},
    "dashboard.connect_messenger": {"en": "Connect Facebook Page", "ar": "ربط صفحة فيسبوك"},
    "dashboard.instagram_connected": {"en": "Instagram connected", "ar": "إنستغرام متصل"},
    "dashboard.manage_catalog": {"en": "Manage catalog", "ar": "إدارة الكتالوج"},
    "dashboard.manage_rules": {"en": "Rules & Autonomy", "ar": "القواعد والاستقلالية"},
    "dashboard.away_heading": {"en": "Availability", "ar": "التوفر"},
    "dashboard.away_status_away": {"en": "Away today", "ar": "غير متاح اليوم"},
    "dashboard.away_status_active": {"en": "Replying normally", "ar": "الرد يعمل بشكل طبيعي"},
    "dashboard.away_checkbox_label": {
        "en": "I'm not available today — auto-reply to everyone instead",
        "ar": "غير متاح اليوم — رد تلقائي على الجميع بدلاً من ذلك",
    },
    "dashboard.away_message_placeholder": {
        "en": "Optional custom message (leave blank for the default)",
        "ar": "رسالة مخصصة اختيارية (اتركها فارغة لاستخدام الرسالة الافتراضية)",
    },
    "dashboard.away_save": {"en": "Save", "ar": "حفظ"},
    "dashboard.usage_heading": {"en": "Usage this period", "ar": "الاستخدام لهذه الفترة"},
    "dashboard.over_cap": {"en": "Over cap", "ar": "تجاوز الحد"},
    "dashboard.messages_suffix": {"en": "messages", "ar": "رسالة"},
    "dashboard.needs_reply_heading": {"en": "Needs your reply", "ar": "بحاجة لردك"},
    "dashboard.needs_reply_empty": {
        "en": "Nothing waiting on you right now.",
        "ar": "لا يوجد شيء بانتظارك الآن.",
    },
    "dashboard.needs_approval_heading": {"en": "Needs your approval", "ar": "بحاجة لموافقتك"},
    "dashboard.needs_approval_empty": {
        "en": "No same-day commitments waiting on you right now.",
        "ar": "لا توجد التزامات توصيل بنفس اليوم بانتظارك الآن.",
    },
    "dashboard.auto_approved_heading": {
        "en": "Recently auto-approved",
        "ar": "تمت الموافقة عليها تلقائياً مؤخراً",
    },
    "dashboard.auto_approved_subtitle": {
        "en": "The agent has learned these delivery windows are reliable and sent them "
        "without waiting on you.",
        "ar": "تعلّم الوكيل أن مواعيد التوصيل هذه موثوقة وأرسلها دون انتظار موافقتك.",
    },
    "dashboard.delivery_word": {"en": "delivery", "ar": "توصيل"},
    "dashboard.recent_conversations_heading": {
        "en": "Recent conversations",
        "ar": "المحادثات الأخيرة",
    },
    "dashboard.download_excel": {"en": "Download as Excel", "ar": "تنزيل كملف إكسل"},
    "dashboard.no_conversations": {"en": "No conversations yet.", "ar": "لا توجد محادثات بعد."},
    # --- escalation.html ---
    "escalation.send_reply": {"en": "Send reply", "ar": "إرسال الرد"},
    # --- approval.html ---
    "approval.approve_heading": {"en": "Approve", "ar": "الموافقة"},
    "approval.send_reply": {"en": "Send reply", "ar": "إرسال الرد"},
    "approval.reject_heading": {"en": "Reject", "ar": "الرفض"},
    "approval.reject_button": {
        "en": "Not approved — tell customer tomorrow",
        "ar": "غير موافق — إخبار الزبون بالغد",
    },
    # Pre-filled, editable draft for the reject form — customer-facing text, not just chrome,
    # but translated the same way since an Arabic-dashboard owner's customers are typically
    # Arabic-speaking too; the owner can always edit it before sending either way.
    "approval.reject_default_text": {
        "en": "Sorry, that delivery time isn't approved — we can get it to you tomorrow instead.",
        "ar": "عذراً، موعد التوصيل هذا غير معتمد — يمكننا توصيله لك غداً بدلاً من ذلك.",
    },
    # --- catalog.html ---
    "catalog.heading": {"en": "Catalog", "ar": "الكتالوج"},
    "catalog.products_heading": {"en": "Products", "ar": "المنتجات"},
    "catalog.add_product": {"en": "+ Add product", "ar": "+ إضافة منتج"},
    "catalog.no_products": {"en": "No products yet.", "ar": "لا توجد منتجات بعد."},
    "catalog.promotions_heading": {"en": "Promotions", "ar": "العروض"},
    "catalog.add_promotion": {"en": "+ Add promotion", "ar": "+ إضافة عرض"},
    "catalog.no_promotions": {"en": "No promotions yet.", "ar": "لا توجد عروض بعد."},
    "catalog.until": {"en": "until", "ar": "حتى"},
    # --- product_form.html ---
    "product_form.edit_title": {"en": "Edit product", "ar": "تعديل المنتج"},
    "product_form.add_title": {"en": "Add product", "ar": "إضافة منتج"},
    "product_form.name_label": {"en": "Name", "ar": "الاسم"},
    "product_form.description_label": {"en": "Description", "ar": "الوصف"},
    "product_form.price_label": {"en": "Price (JOD)", "ar": "السعر (دينار)"},
    "product_form.stock_status_label": {"en": "Stock status", "ar": "حالة المخزون"},
    "product_form.stock_status_hint": {
        "en": "in_stock, out_of_stock, or made_to_order",
        "ar": "in_stock أو out_of_stock أو made_to_order",
    },
    "product_form.variants_label": {"en": "Variants", "ar": "الأصناف"},
    "product_form.variants_hint": {
        "en": 'Optional — e.g. "box of 6:in_stock; box of 12:out_of_stock"',
        "ar": 'اختياري — مثال: "box of 6:in_stock; box of 12:out_of_stock"',
    },
    "product_form.save": {"en": "Save changes", "ar": "حفظ التغييرات"},
    "product_form.delete": {"en": "Delete product", "ar": "حذف المنتج"},
    # --- promotion_form.html ---
    "promotion_form.edit_title": {"en": "Edit promotion", "ar": "تعديل العرض"},
    "promotion_form.add_title": {"en": "Add promotion", "ar": "إضافة عرض"},
    "promotion_form.title_label": {"en": "Title", "ar": "العنوان"},
    "promotion_form.description_label": {"en": "Description", "ar": "الوصف"},
    "promotion_form.discount_label": {"en": "Discount", "ar": "نسبة الخصم"},
    "promotion_form.discount_hint": {
        "en": 'Free text — e.g. "20% off" or "3 for 10 JOD"',
        "ar": 'نص حر — مثال: "خصم 20%" أو "3 مقابل 10 دنانير"',
    },
    "promotion_form.applies_to_label": {"en": "Applies to", "ar": "ينطبق على"},
    "promotion_form.applies_to_hint": {
        "en": "Optional — which product or category this covers",
        "ar": "اختياري — أي منتج أو فئة يغطيها هذا العرض",
    },
    "promotion_form.starts_label": {"en": "Starts", "ar": "يبدأ"},
    "promotion_form.ends_label": {"en": "Ends", "ar": "ينتهي"},
    "promotion_form.ends_hint": {
        "en": "Amman time — the agent stops mentioning this promotion after it ends",
        "ar": "بتوقيت عمّان — يتوقف الوكيل عن ذكر هذا العرض بعد انتهائه",
    },
    "promotion_form.save": {"en": "Save changes", "ar": "حفظ التغييرات"},
    "promotion_form.delete": {"en": "Delete promotion", "ar": "حذف العرض"},
    # --- rules.html (Doc 3 roadmap, partner meeting 2026-09-01) ---
    "rules.heading": {"en": "Rules & Autonomy", "ar": "القواعد والاستقلالية"},
    "rules.autonomy_heading": {"en": "Autonomy", "ar": "الاستقلالية"},
    "rules.autonomy_description": {
        "en": "Choose which situations the agent can reply to on its own, and how sensitive "
        "it is to negative tone.",
        "ar": "اختر الحالات التي يمكن للوكيل الرد عليها بمفرده، ومدى حساسيته للنبرة السلبية.",
    },
    "rules.category_price_negotiation": {"en": "Price negotiation", "ar": "التفاوض على السعر"},
    "rules.category_refund_or_complaint": {
        "en": "Refunds & complaints",
        "ar": "الاسترجاع والشكاوى",
    },
    "rules.category_competitor_mention": {
        "en": "Competitor mentions",
        "ar": "ذكر المنافسين",
    },
    "rules.category_legal_threat": {"en": "Legal threats", "ar": "التهديدات القانونية"},
    "rules.category_hint": {
        "en": "Checked = still needs your approval. Unchecked = the agent replies on its own "
        "when it's confident.",
        "ar": "محدد = ما زال يحتاج موافقتك. غير محدد = يرد الوكيل بمفرده عندما يكون واثقاً.",
    },
    "rules.sensitivity_label": {
        "en": "Sensitivity to negative tone",
        "ar": "الحساسية للنبرة السلبية",
    },
    "rules.sensitivity_cautious": {
        "en": "Cautious — escalate more often",
        "ar": "حذر — تصعيد أكثر",
    },
    "rules.sensitivity_balanced": {"en": "Balanced (default)", "ar": "متوازن (افتراضي)"},
    "rules.sensitivity_permissive": {
        "en": "Permissive — escalate less often",
        "ar": "متساهل — تصعيد أقل",
    },
    "rules.save_autonomy": {"en": "Save autonomy settings", "ar": "حفظ إعدادات الاستقلالية"},
    "rules.delivery_heading": {"en": "Delivery restrictions", "ar": "قيود التوصيل"},
    "rules.delivery_description": {
        "en": "Locations the agent should never promise delivery to — one per line.",
        "ar": "المواقع التي يجب ألا يعد الوكيل بالتوصيل إليها — موقع واحد في كل سطر.",
    },
    "rules.save_delivery": {"en": "Save delivery restrictions", "ar": "حفظ قيود التوصيل"},
    "rules.custom_heading": {"en": "Custom rules", "ar": "قواعد مخصصة"},
    "rules.custom_description": {
        "en": "Write a rule in plain language. We review every custom rule before it goes "
        "live, to make sure the agent behaves the way you expect.",
        "ar": "اكتب قاعدة بلغة بسيطة. نراجع كل قاعدة مخصصة قبل تفعيلها للتأكد من أن الوكيل "
        "سيتصرف كما تتوقع.",
    },
    "rules.custom_submit": {"en": "Submit for review", "ar": "إرسال للمراجعة"},
    "rules.custom_empty": {"en": "No custom rules yet.", "ar": "لا توجد قواعد مخصصة بعد."},
    # --- conversations (Doc 3 roadmap, partner meeting 2026-09-01: full conversation view) ---
    "conversations.view_all": {"en": "View all", "ar": "عرض الكل"},
    "conversations.heading": {"en": "All conversations", "ar": "كل المحادثات"},
    "conversations.empty": {"en": "No conversations yet.", "ar": "لا توجد محادثات بعد."},
    "conversations.prev_page": {"en": "Previous", "ar": "السابق"},
    "conversations.next_page": {"en": "Next", "ar": "التالي"},
    "conversations.page_label": {"en": "Page", "ar": "صفحة"},
    "conversations.send_label": {
        "en": "Send a message to this customer",
        "ar": "أرسل رسالة لهذا الزبون",
    },
    "conversations.send_button": {"en": "Send", "ar": "إرسال"},
    "conversations.pending_elsewhere_escalation": {
        "en": "This conversation has an escalation waiting on your reply —",
        "ar": "هاي المحادثة فيها تصعيد بينتظر ردك —",
    },
    "conversations.pending_elsewhere_approval": {
        "en": "This conversation has an order waiting on your approval —",
        "ar": "هاي المحادثة فيها طلب بينتظر موافقتك —",
    },
    "conversations.pending_elsewhere_link": {
        "en": "resolve it there",
        "ar": "عالجها من هناك",
    },
    # --- billing (Doc 3 roadmap, Phase 4: manual/CliQ-style billing) ---
    "billing.heading": {"en": "Billing", "ar": "الفوترة"},
    "billing.current_plan_label": {"en": "Current plan", "ar": "الخطة الحالية"},
    "billing.change_plan_intro": {
        "en": "Want to change your plan? Pick a new one below.",
        "ar": "بدك تغيّر خطتك؟ اختار وحدة جديدة تحت.",
    },
    "billing.pending_intro": {
        "en": "We've received your request for",
        "ar": "استلمنا طلبك لخطة",
    },
    "billing.payment_instructions_label": {"en": "Payment instructions", "ar": "تعليمات الدفع"},
    "billing.instructions_not_configured": {
        "en": (
            "Payment details aren't set up yet — contact OptiGnosis directly to complete "
            "your subscription."
        ),
        "ar": "تفاصيل الدفع لسا ما انضبطت — تواصل مع OptiGnosis مباشرة لإكمال اشتراكك.",
    },
    "billing.reference_label": {
        "en": "Reference (include with your transfer)",
        "ar": "الرقم المرجعي (أرفقه مع تحويلتك)",
    },
    "billing.trialing_intro": {
        "en": "Pick a plan below to get started.",
        "ar": "اختار خطة تحت عشان تبلش.",
    },
    "billing.jod_per_month": {"en": "JOD/mo", "ar": "دينار/شهر"},
    "billing.messages_per_month": {"en": "messages/mo", "ar": "رسالة/شهر"},
    "billing.request_plan_button": {"en": "Request this plan", "ar": "اطلب هاي الخطة"},
    "status.payment_pending": {"en": "Payment pending", "ar": "بانتظار الدفع"},
    "status.trialing": {"en": "Trial", "ar": "تجريبي"},
    # --- status/badge values (real enums + conventional stock_status values) ---
    "status.auto": {"en": "Auto", "ar": "تلقائي"},
    "status.owner_handled": {"en": "Owner handled", "ar": "بمعالجة المالك"},
    "status.closed": {"en": "Closed", "ar": "مغلق"},
    "status.pending": {"en": "Pending", "ar": "قيد الانتظار"},
    "status.resolved": {"en": "Resolved", "ar": "تم الحل"},
    "status.approved": {"en": "Approved", "ar": "تمت الموافقة"},
    "status.rejected": {"en": "Rejected", "ar": "مرفوض"},
    "status.in_stock": {"en": "In stock", "ar": "متوفر"},
    "status.out_of_stock": {"en": "Out of stock", "ar": "غير متوفر"},
    "status.made_to_order": {"en": "Made to order", "ar": "يُحضّر عند الطلب"},
    "status.expired": {"en": "expired", "ar": "منتهي"},
    "status.active": {"en": "active", "ar": "فعّال"},
}


def get_lang(request: Request) -> str:
    lang = request.session.get("lang", DEFAULT_LANGUAGE)
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def t(lang: str, key: str) -> str:
    """Falls back to English if a key exists but the language entry doesn't, and to the raw
    key itself if the key isn't a translation key at all (e.g. a seller's own free-text
    stock_status value passed through `status.<value>` — displays unchanged rather than
    erroring, since stock_status is genuinely free text, not a strict enum).
    """
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get(DEFAULT_LANGUAGE, key))


def t_status(lang: str, value: str) -> str:
    """For displaying a status/stock_status value as text (badges) — unlike t(), falls back to
    the raw value itself (not a "status.<value>" key) when there's no translation entry, since
    stock_status in particular is genuinely free text a seller can type anything into.
    """
    entry = TRANSLATIONS.get(f"status.{value}")
    if entry is None:
        return value
    return entry.get(lang, entry.get(DEFAULT_LANGUAGE, value))

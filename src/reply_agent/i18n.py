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
    # --- dashboard.html ---
    "dashboard.back_all_businesses": {"en": "All businesses", "ar": "جميع الأعمال"},
    "dashboard.whatsapp_connected": {"en": "WhatsApp connected", "ar": "واتساب متصل"},
    "dashboard.connect_whatsapp": {"en": "Connect WhatsApp", "ar": "ربط واتساب"},
    "dashboard.messenger_connected": {"en": "Messenger connected", "ar": "ماسنجر متصل"},
    "dashboard.connect_messenger": {"en": "Connect Facebook Page", "ar": "ربط صفحة فيسبوك"},
    "dashboard.instagram_connected": {"en": "Instagram connected", "ar": "إنستغرام متصل"},
    "dashboard.manage_catalog": {"en": "Manage catalog", "ar": "إدارة الكتالوج"},
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

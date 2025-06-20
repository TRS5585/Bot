import os
import asyncio
import pdfplumber
from datetime import datetime
from telegram import Update, Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import nest_asyncio

PDF_DIR = "./pdfs"
LOG_FILE = "log.txt"
TOKEN = "8011191507:AAF3Vwb_Bho1fNl4G5aqfzmXE30GML_L3D8"  # Ton Token
OWNER_CHAT_ID = 7420143709  # Ton ID

ALL_LINES = {}
ACADEMIES = {}
ADD_PDF_WAITING = {}

CHOOSING_ACADEMY, ENTERING_SEAT = range(2)

# 📥 Chargement de tous les PDF
def reload_all_pdfs():
    ALL_LINES.clear()
    ACADEMIES.clear()
    for filename in os.listdir(PDF_DIR):
        if filename.endswith(".pdf"):
            name = filename.replace(".pdf", "").replace("_", " ").title()
            path = os.path.join(PDF_DIR, filename)
            try:
                with pdfplumber.open(path) as pdf:
                    lines = []
                    for page in pdf.pages:
                        table = page.extract_table()
                        if table:
                            for row in table:
                                lines.append(" | ".join(cell or "" for cell in row))
                    ACADEMIES[name] = filename
                    ALL_LINES[name] = lines
                    print(f"✅ Chargé : {name} ({len(lines)} lignes)")
            except Exception as e:
                print(f"❌ Erreur avec {filename} : {e}")

# 🔍 Recherche d'un candidat
def search_candidate(seat_number, acad):
    return next((line for line in ALL_LINES.get(acad, []) if seat_number in line), None)

# 🧾 Journalisation
def log_activity(username, acad, seat_number, result):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {username} | {acad} | {seat_number} → {result}\n")

# ▶️ /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[a] for a in ACADEMIES.keys()]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("📚 Sélectionne ton académie :", reply_markup=markup)
    return CHOOSING_ACADEMY

async def choose_academy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    acad = update.message.text
    if acad in ACADEMIES:
        context.user_data["acad"] = acad
        await update.message.reply_text("✏️ Entre ton numéro de place :", reply_markup=ReplyKeyboardRemove())
        return ENTERING_SEAT
    else:
        await update.message.reply_text("❌ Académie invalide.")
        return CHOOSING_ACADEMY

async def enter_seat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seat_number = update.message.text.strip()
    acad = context.user_data.get("acad")
    user = update.message.from_user
    username = user.username or user.full_name

    if seat_number.isdigit():
        result = search_candidate(seat_number, acad)
        reply = f"🎉 Résultat trouvé :\n{result}" if result else "❌ Numéro de place non trouvé."
        await update.message.reply_text(reply)
        log_activity(username, acad, seat_number, reply)

        keyboard = [["🔙 Changer d’académie"]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("🔁 Tape un autre numéro ou change d’académie :", reply_markup=markup)
        return ENTERING_SEAT

    elif "Changer" in seat_number:
        return await start(update, context)
    else:
        await update.message.reply_text("❗️ Numéro invalide.")
        return ENTERING_SEAT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⛔️ Conversation annulée.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# 🛠️ Commandes d’admin

async def addpdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    if len(context.args) < 1:
        await update.message.reply_text("❗️ Utilise : /addpdf NomDeLAcadémie")
        return
    name = " ".join(context.args).title()
    ADD_PDF_WAITING[update.effective_user.id] = name
    await update.message.reply_text(f"📎 Envoie maintenant le fichier PDF pour : {name}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_CHAT_ID or user_id not in ADD_PDF_WAITING:
        return
    acad_name = ADD_PDF_WAITING.pop(user_id)
    file = update.message.document
    if not file.file_name.endswith(".pdf"):
        await update.message.reply_text("❌ Seuls les fichiers PDF sont acceptés.")
        return

    filename = acad_name.lower().replace(" ", "_") + ".pdf"
    path = os.path.join(PDF_DIR, filename)
    file_path = await file.get_file()
    await file_path.download_to_drive(path)

    # Recharger ce PDF
    try:
        with pdfplumber.open(path) as pdf:
            lines = []
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    for row in table:
                        lines.append(" | ".join(cell or "" for cell in row))
            ACADEMIES[acad_name] = filename
            ALL_LINES[acad_name] = lines
        await update.message.reply_text(f"✅ PDF chargé et associé à : {acad_name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur de chargement : {e}")

async def removepdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    if len(context.args) < 1:
        await update.message.reply_text("❗️ Utilise : /removepdf NomDeLAcadémie")
        return
    name = " ".join(context.args).title()
    filename = ACADEMIES.get(name)
    if not filename:
        await update.message.reply_text("❌ Académie introuvable.")
        return
    try:
        os.remove(os.path.join(PDF_DIR, filename))
        ACADEMIES.pop(name)
        ALL_LINES.pop(name)
        await update.message.reply_text(f"✅ {name} supprimé.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur : {e}")

async def reloadpdfs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    reload_all_pdfs()
    await update.message.reply_text("🔄 Tous les PDF ont été rechargés.")

# 🚀 Lancer le bot
async def start_bot():
    reload_all_pdfs()
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_ACADEMY: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_academy)],
            ENTERING_SEAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_seat)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=False
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("addpdf", addpdf))
    app.add_handler(CommandHandler("removepdf", removepdf))
    app.add_handler(CommandHandler("reloadpdfs", reloadpdfs))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))

    print("✅ Bot lancé.")
    await Bot(token=TOKEN).send_message(chat_id=OWNER_CHAT_ID, text="🟢 Le bot est en ligne avec gestion des PDF activée.")
    await app.run_polling()

# ▶️ Lancement
if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(start_bot())
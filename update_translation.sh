#!/bin/bash
# ===========================================
# Farm Shop – Translation Update Utility
# ===========================================

set -e

echo
echo "🌍 Extracting new translation strings..."
pybabel extract -F babel.cfg -o messages.pot .

echo
echo "🔄 Updating existing translation catalogs..."
pybabel update -i messages.pot -d translations

echo
echo "📝 Reminder: edit your .po files if new text was found!"
echo "    Example: translations/pt/LC_MESSAGES/messages.po"
read -p "Press ENTER to continue after editing .po files..."

echo
echo "🧵 Compiling translations to .mo files..."
pybabel compile -d translations

echo
echo "✅ All done! Translations have been updated and compiled."
echo

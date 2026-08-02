# bot/localization.py

LOCALIZATION = {
    "ru": {
        "status_title": "📊 <b>Статус подписки</b>\n\n",
        "status_active": "🟢 Активна",
        "status_paused": "🔴 Приостановлена",
        "status_lbl": "Статус",
        "profile_lbl": "📧 Профиль",
        "traffic_lbl": "📈 Потребление трафика:\n",
        "used_lbl": "Использовано",
        "rem_lbl": "Осталось",
        "total_lbl": "Выделенная емкость",
        "days_lbl": "⏳ Срок действия",
        "days_unit": "дн.",
        "welcome": "👋 <b>Добро пожаловать в Ulysses VPN, {name}!</b>\n\n"
                   "Ваш персональный защищенный туннель полностью готов к работе.\n"
                   "Используйте интерактивное меню ниже для управления подпиской:\n\n"
                   "👉 <i>Выберите интересующий вас раздел:</i>",
        "support_prompt": "🆘 Пожалуйста, напишите ваш вопрос в ответ на это сообщение. Инженеры поддержки сразу получат его:",
        "ticket_success": "✅ Ваше обращение успешно зарегистрировано под №{num} и передано дежунному инженеру!",
        "ticket_error": "⚠️ Сервис техподдержки временно перегружен. Пожалуйста, попробуйте отправить сообщение чуть позже.",
        "lang_changed": "✅ Язык интерфейса успешно изменен на Русский!",
        "choose_lang_title": "🌐 <b>Настройка языка / Language Settings</b>\n\nВыберите удобный язык интерфейса ниже:",
        "about_text": "ℹ️ <b>О сервисе</b>\n\nНаш сервис предоставляет безопасные удаленные прокси-каналы для ИТ-специалистов, разработчиков и сетевых администраторов.\n\n<b>Назначение сервиса:</b>\n• Безопасное тестирование веб-приложений из различных локаций.\n• Шифрование исходящего интернет-трафика при работе в незащищенных публичных сетях Wi-Fi.\n• Организация защищенных туннелей для удаленного администрирования серверов.\n\n<b>Как это работает:</b>\nПосле аренды доступа вы получаете индивидуальный токен (конфигурационный файл) для подключения к удаленному узлу и краткую техническую инструкцию по установке соединения.",
        "rules_text": "📜 <b>Публичная оферта</b>:\nусловия договора на цифровые услуги и цифровые товары «Лаборатория Улисс». Оплата и/или оформление заказа означает акцепт оферты.\n\nПолный текст оферты доступен по адресу: <a href='https://ulysses.best'>https://ulysses.best</a>",
        "support_text": "🆘 <b>Служба технической поддержки</b>\n\nЕсли у вас возникли проблемы с настройкой подключения, оплатой заказа или активацией ключа, наша команда готова вам помочь!\n\n<b>Контакты для связи:</b>\n• Наш официальный канал поддержки - здесь.\n• Время работы: ежедневно с 09:00 до 21:00 (по МСК).\n\n<b>Важная информация по платежам:</b>\nЕсли ваш платёж через систему оплаты прошёл, но баланс или доступ в боте не обновился в течение 10 минут, пожалуйста, пришлите в чат поддержки <i>снимок экрана (скриншот) квитанции об оплате</i> или ID транзакции из истории платежей. Мы активируем ваш доступ вручную."
    },
    "en": {
        "status_title": "📊 <b>Subscription Status</b>\n\n",
        "status_active": "🟢 Active",
        "status_paused": "🔴 Suspended",
        "status_lbl": "Status",
        "profile_lbl": "📧 Profile",
        "traffic_lbl": "📈 Traffic Consumption:\n",
        "used_lbl": "Used",
        "rem_lbl": "Remaining",
        "total_lbl": "Total Capacity",
        "days_lbl": "⏳ Valid until",
        "days_unit": "days",
        "welcome": "👋 <b>Welcome to Ulysses VPN, {name}!</b>\n\n"
                   "Your personal secure tunnel is fully ready for operation.\n"
                   "Use the interactive menu below to manage your subscription:\n\n"
                   "👉 <i>Select the section you are interested in:</i>",
        "support_prompt": "🆘 Please write your question in reply to this message. Support engineers will receive it immediately:",
        "ticket_success": "✅ Your ticket has been successfully registered as #{num} and forwarded to the engineer on duty!",
        "ticket_error": "⚠️ The technical support service is temporarily overloaded. Please try sending your message a bit later.",
        "lang_changed": "✅ Interface language has been changed to English!",
        "choose_lang_title": "🌐 <b>Language Settings / Настройка языка</b>\n\nSelect your preferred interface language below:",
        "about_text": "ℹ️ <b>About Service</b>\n\nOur service provides secure remote proxy channels for IT specialists, developers, and network administrators.\n\n<b>Service Purpose:</b>\n• Secure testing of web applications from various locations.\n• Encryption of outbound internet traffic when working in unsecured public Wi-Fi networks.\n• Organization of secure tunnels for remote server administration.\n\n<b>How it works:</b>\nAfter renting access, you will receive an individual token (configuration file) to connect to a remote node and brief technical instructions for establishing a connection.",
        "rules_text": "📜 <b>Public Offer</b>:\nTerms of service for digital services and digital goods of 'Ulysses Lab'. Payment and/or placing an order implies acceptance of the offer.\n\nFull text is available here: <a href='https://ulysses.best'>https://ulysses.best</a>",
        "support_text": "🆘 <b>Technical Support Service</b>\n\nIf you encounter any problems with configuring the connection, payment, or key activation, our team is ready to help!\n\n<b>Contacts:</b>\n• Our official support channel is here.\n• Working hours: daily from 09:00 to 21:00 (MSK).\n\n<b>Important Payment Information:</b>\nIf your payment went through, but the balance or access in the bot has not updated within 10 minutes, please send a <i>screenshot of the payment receipt</i> or the transaction ID to the support chat. We will activate your access manually."
    }
}

BILLING_LOC = {
    "ru": {
        "loading": "⏳ <i>Формирую безопасный запрос к серверу, пожалуйста, подождите...</i>",
        "api_error": "❌ Сервер биллинга отклонил операцию. Попробуйте позже.",
        "tariff_title": "🔌 <b>Доступные тарифные планы Ulysses VPN:</b>\n\n<i>Выберите интересующий вас период подписки:</i>",
        "tariff_load_err": "❌ Не удалось загрузить тарифную сетку с сервера.",
        "choose_currency": "💳 <b>Выбран тариф: {slug}</b>\n\nВыберите валюту оплаты:",
        "invoice_created": "💳 <b>Счет на оплату успешно сформирован!</b>\n\nСумма к оплате: <b>{amount:.2f} {currency}</b>\n\nНажмите кнопку ниже, чтобы перейти на безопасную страницу оплаты Platega и выбрать удобный способ (карта, СБП, крипта).",
        "btn_pay": "🚀 Перейти к оплате",
        "btn_change": "⬅️ Изменить тариф",
        "free_success": "🎉 <b>Ваш бесплатный тест-драйв Ulysses VPN успешно активирован!</b>\n\n"
                        "🔑 <b>Ваша персональная ссылка подписки:</b>\n"
                        "<code>{link}</code>\n\n"
                        "⏳ Срок действия: до <b>{exp}</b>\n\n"
                        "📥 <b>Краткая инструкция по подключению:</b>\n"
                        "1. Нажмите на поле со ссылкой выше, чтобы скопировать её.\n"
                        "2. Скачайте и запустите приложение <b>Hiddify Next</b> на вашем устройстве.\n"
                        "3. Нажмите кнопку <b>'Добавить профиль'</b> (или значок Плюса) ➔ выберите вариант <b>'Из буфера обмена'</b>.\n"
                        "4. Нажмите круглую кнопку подключения в центре экрана.\n\n"
                        "🚀 Приятного и безопасного полета без блокировок!"
    },
    "en": {
        "loading": "⏳ <i>Generating a secure request to the server, please wait...</i>",
        "api_error": "❌ The billing server rejected the operation. Please try again later.",
        "tariff_title": "🔌 <b>Available Ulysses VPN tariff plans:</b>\n\n<i>Select your preferred subscription period:</i>",
        "tariff_load_err": "❌ Failed to load the tariff grid from the server.",
        "choose_currency": "💳 <b>Selected tariff: {slug}</b>\n\nSelect payment currency:",
        "invoice_created": "💳 <b>Invoice successfully created!</b>\n\nAmount to pay: <b>{amount:.2f} {currency}</b>\n\nClick the button below to proceed to the secure Platega payment page and select your convenient method (card, SBP, crypto).",
        "btn_pay": "🚀 Proceed to Payment",
        "btn_change": "⬅️ Change Plan",
        "free_success": "🎉 <b>Your free Ulysses VPN trial has been successfully activated!</b>\n\n"
                        "🔑 <b>Your personal subscription link:</b>\n"
                        "<code>{link}</code>\n\n"
                        "⏳ Valid until: <b>{exp}</b>\n\n"
                        "📥 <b>Quick setup guide:</b>\n"
                        "1. Tap on the link field above to copy it.\n"
                        "2. Download and launch the <b>Hiddify Next</b> app on your device.\n"
                        "3. Click the <b>'Add Profile'</b> button (or Plus icon) ➔ select the <b>'From Clipboard'</b> option.\n"
                        "4. Press the round connection button in the center of the screen.\n\n"
                        "🚀 Have a pleasant and safe connection without restrictions!"
    }
}

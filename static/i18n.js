// Site language. English stays the default for PayPal's judges; a browser set to Ukrainian, or the EN · UA
// switch, shows the site in Ukrainian. Static pages mark text with data-i18n keys; app pages wrap
// strings in L(); live texts from the server (ledger lines, AI verdicts, bank categories) go through dyn() and are
// translated on demand by /api/translate, then remembered in this browser.
const LANGS = { en: "EN", uk: "UA" };
const LANG = (() => {
  // ?lang=uk in a shared link wins and is remembered
  const asked = new URLSearchParams(location.search).get("lang");
  if (LANGS[asked]) { try { localStorage.setItem("lang", asked); } catch (e) { /* storage blocked */ } return asked; }
  try { const saved = localStorage.getItem("lang"); if (LANGS[saved]) return saved; } catch (e) { /* storage blocked */ }
  for (const l of navigator.languages || [navigator.language || "en"]) {
    const code = String(l).slice(0, 2).toLowerCase();
    if (LANGS[code]) return code;
  }
  return "en";
})();
document.documentElement.lang = LANG;
const LOCALE = { en: "en-GB", uk: "uk-UA" }[LANG];

const I18N = {
  uk: {
    // ---- landing ----
    "title.landing": "Proof of Good · Допомога волонтерам, прозора до копійки",
    "nav.how": "Як це працює", "nav.proof": "Докази", "nav.faq": "Питання", "nav.campaigns": "Збори", "nav.try": "Спробувати",
    "nav.full": "Пройти весь шлях", "nav.ledger": "Реєстр", "nav.volunteer": "Кабінет волонтера", "nav.source": "Код",
    "nav.privacy": "Конфіденційність", "nav.terms": "Умови", "nav.home": "Головна",
    "hero.h1": "Допомога волонтерам.<br>Прозоро до копійки.",
    "hero.lead": "Ваша пожертва зберігається на PayPal і надходить українському волонтеру по одній статті бюджету, на картку, кожен платіж з якої перевіряє ШІ. Якщо гроші використають не за призначенням, решта повернеться вам.",
    "cta": "Пройти весь шлях за 2 хвилини",
    "hero.p1": "Кожен платіж карткою перевіряється приблизно за 10 секунд",
    "hero.p2": "Працює на PayPal Orders, Payouts і Refunds",
    "rp.title": "Прозора картка", "rp.replay": "Повторити", "rp.lbl": "Виплачено на питну воду", "rp.card": "Тестова картка •• 2026",
    "rp.1b": "−₴440 у супермаркеті", "rp.1s": "Відповідає воді для укриття",
    "rp.2b": "Фото відхилено за 15,3 с", "rp.2s": "Картинка з інтернет-магазину, а не фото з місця",
    "rp.3b": "−₴230 готівкою в банкоматі", "rp.3s": "Гроші пішли не за призначенням, картку одразу заморожено",
    "rp.4b": "$2.00 повернуто донору", "rp.foot": "Повтор справжнього прогону в пісочниці PayPal, 27 жовтня 2026",
    "pr.eyebrow": "Проблема",
    "pr.h2": "Люди хочуть допомагати. Вони просто не бачать, куди йдуть гроші.",
    "pr.p1": "Після кожної біди з'являються фейкові збори, і чесні волонтери через них втрачають донорів. Банка показує, скільки надійшло. <b>Але ніколи не показує, що купили.</b>",
    "pr.p2": "Proof of Good показує і те, і те. Волонтер платить прозорою карткою, банк повідомляє про кожен платіж, а ШІ перевіряє його <b>до того, як рушить наступна частина грошей.</b>",
    "pr.s1": "американців кажуть, що довіра обов'язкова, перш ніж жертвувати.",
    "pr.s2": "мають високу довіру до благодійних організацій.",
    "pr.cite": "Give.org <a href='https://give.org/donortrust' target='_blank' rel='noopener'>Donor Trust Report 2026</a>, опитування понад 1 500 дорослих у США, грудень 2025.",
    "tagline": "Волонтери отримують гроші.<br>Донори бачать кожен платіж.<br>Ніхто не отримує карт-бланш.",
    "bn.eyebrow": "Чому це працює", "bn.h2": "Безпечно для донорів. Чесно для волонтерів.",
    "bn.1t": "Жодного карт-бланшу", "bn.1p": "На картці лише одна стаття бюджету за раз, тож у найгіршому разі ризикує одна стаття, а не весь збір.",
    "bn.2t": "Кожен платіж публічний", "bn.2p": "Банк повідомляє про кожен платіж карткою, а ШІ звіряє його з метою приблизно за 10 секунд.",
    "bn.3t": "Доказ відкриває наступну частину", "bn.3p": "Фото речі там, де її використовують, відкриває наступну статтю бюджету. На обіцянки нічого не виплачується.",
    "bn.4t": "Зловживання зупиняється одразу", "bn.4p": "Зняття готівки, перекази з картки на картку й азартні ігри заморожують картку, а PayPal повертає кожному донору його частку.",
    "bn.5t": "Волонтеру не потрібні власні гроші", "bn.5p": "Перша стаття надходить на картку, щойно її зібрано. Доказ потрібен уже після покупки.",
    "hw.eyebrow": "Як це працює", "hw.h2": "Три кроки між пожертвою і генератором у лікарні.",
    "hw.1t": "Пожертвуйте", "hw.1p": "Платіть через PayPal або будь-якою банківською карткою. Гроші зберігаються на PayPal, і поки що їх ні в кого немає.",
    "hw.2t": "Витрачайте прозорою карткою", "hw.2p": "Одна стаття бюджету надходить на картку збору волонтера. Банк повідомляє про кожен платіж, а ШІ перевіряє його одразу.",
    "hw.3t": "Підтвердьте й відкрийте наступну", "hw.3p": "Фото покупки закриває статтю й відкриває наступну. Зловживання повертає решту донорам.",
    "pf.eyebrow": "Докази", "pf.h2": "Цифри з живого демо, а не обіцянки.",
    "pf.lead": "Пораховано з публічного реєстру просто зараз. Демо працює в пісочниці PayPal, тож кожна цифра нижче означає справжні запити до API з тестовими грошима.",
    "pf.f1": "<b>12 категорій продавців заморожують картку одразу:</b> готівка, перекази з картки на картку, крипта, азартні ігри, бари й ювелірка.",
    "pf.f2": "<b>Кожне фото проходить від 5 до 7 перевірок:</b> повторне використання, дата зйомки, програми для редагування, мітки ШІ, сама річ, справжнє фото, збіг із покупкою.",
    "pf.f3": "<b>Фейковий скриншот із магазину відхилено за 15,3 секунди,</b> а причини показано і волонтеру, і донорам.",
    "pf.f4": "<b>Кожен номер PayPal у реєстрі є справжньою транзакцією в пісочниці,</b> яку можна перевірити, а код відкритий на GitHub.",
    "pf.note": "Усі події є в <a href='/ledger'>публічному реєстрі</a>, а <a href='https://github.com/V1zual/proof-of-good' target='_blank' rel='noopener'>код</a> відкритий.",
    "fq.eyebrow": "Питання", "fq.h2": "Питання, які донори ставлять першими.",
    "sc.eyebrow": "Як це виглядає", "sc.h2": "Кожен екран з одного справжнього прогону в пісочниці PayPal.",
    "sc.t1": "Сторінка збору", "sc.t2": "Кабінет волонтера", "sc.t3": "Перевірка фото ШІ", "sc.t4": "Заморожена картка", "sc.t5": "Публічний реєстр", "sc.t6": "Сторінка донора",
    "sc.c1": "Донори бачать, скільки зібрано, яка стаття бюджету на картці, і кожен платіж карткою з перевіркою ШІ поруч.",
    "sc.c2": "Волонтер бачить залишок на картці для поточної статті бюджету й наступний крок: тут це надіслати фото.",
    "sc.c3": "Кожне фото й чек проходять перевірки. Цю картинку з магазину відхилено, а причини показано донорам.",
    "sc.c4": "Зняття готівки одразу заморозило картку. Більше гроші не виплачуються.",
    "sc.c5": "Кожна пожертва, виплата, платіж карткою, вердикт і повернення в одній таблиці зі справжніми номерами PayPal.",
    "sc.c6": "Кожен донор отримує посилання, яке показує, де зараз кожен його долар: на картці, витрачений і підтверджений або повернутий.",
    "fl.h3": "Простежте $12 від донора до пляшки води",
    "fl.1b": "$12 пожертвувано", "fl.1s": "Оплачено через PayPal і зберігається там. Ні в кого цих грошей ще немає.",
    "fl.2b": "$10 надіслано на картку", "fl.2s": "Перша стаття бюджету, вода для укриття, йде волонтеру.",
    "fl.3b": "−₴440 у супермаркеті", "fl.3s": "Банк повідомляє про платіж, а ШІ приблизно за 10 секунд звіряє його з водою.",
    "fl.4b": "Фото води", "fl.4s": "Зроблене на місці. Воно підтверджує статтю й відкриває наступну.",
    "fl.5b": "$2 ще зберігаються", "fl.5s": "Вони чекають на наступну статтю або повертаються донору.",
    "fl.branch": "<b>Якщо карткою заплатять за щось інше,</b> наприклад зніматимуть готівку, переказуватимуть гроші чи гратимуть в азартні ігри, вона одразу заморожується, а $2, що ще зберігаються, повертаються донору через PayPal Refunds.",
    "fn.h2": "Подивіться весь шлях з тестовими грошима, від пожертви до повернення.",
    "fn.s1": "Відкрийте <a href='/c/try'>тестовий збір</a> і пожертвуйте $10 від тестового покупця, указаного на сторінці.",
    "fn.s2": "Відкрийте <a href='/volunteer?code=TRY-IT'>кабінет волонтера</a> з кодом TRY-IT і оплатіть тестовою карткою в супермаркеті.",
    "fn.s3": "Надішліть фото будь-якої пляшки води й подивіться, як ШІ його перевіряє.",
    "fn.s4": "Натисніть кнопку банкомата й подивіться, як картка заморожується, а гроші повертаються.",
    "fn.lead": "Реєстрація не потрібна. Усе працює в пісочниці PayPal з тестовими грошима.",
    "fn.guarantee": "Якщо гроші використають не за призначенням або доказ так і не надійде, кожному донору автоматично повернеться його частка, що ще зберігається, через PayPal Refunds.",
    "ft.built": "Proof of Good · створено для PayPal AI Hackathon 2026",
    // ---- 404, privacy, terms ----
    "nf.title": "Сторінку не знайдено · Proof of Good", "nf.h1": "Сторінку не знайдено.",
    "nf.lead": "Можливо, посилання застаріле: тестові пожертви зникають, коли демосервер перезапускається. Усе, що існує зараз, є на сторінці зборів і в публічному реєстрі.",
    "nf.back": "На головну", "nf.open": "Відкрити збори",
    "pv.title": "Конфіденційність · Proof of Good", "pv.eyebrow": "Конфіденційність", "pv.h1": "Що цей демосайт зберігає про вас",
    "pv.p1": "Proof of Good працює як демо для хакатону в пісочниці PayPal. Справжні гроші не рухаються, і жоден справжній банківський рахунок на цьому сервері не читається.",
    "pv.p2": "<b>Пожертви.</b> Коли ви жертвуєте з тестового акаунта PayPal, ми зберігаємо ім'я та email, які повертає PayPal, суму й номери PayPal, щоб показати їх у публічному реєстрі та на сторінці вашої пожертви.",
    "pv.p3": "<b>Фото доказів.</b> Фото й чеки, які завантажує волонтер, зберігаються на сервері, публічно показуються поруч зі збором і надсилаються до Gemini API від Google для перевірки.",
    "pv.p4": "<b>Telegram.</b> Якщо ви пишете боту, ми зберігаємо номер вашого чату, щоб надсилати оновлення, на які ви підписалися.",
    "pv.p5": "<b>Як довго.</b> Усе зберігається в тимчасовій базі, яку стирають при кожному перезапуску демосервера. Ми не використовуємо cookies і аналітику; браузер запам'ятовує лише обрану вами мову й уже перекладені тексти.",
    "pv.p6": "Питання: створіть issue на <a href='https://github.com/V1zual/proof-of-good' target='_blank' rel='noopener'>GitHub</a>.",
    "tm.title": "Умови · Proof of Good", "tm.eyebrow": "Умови", "tm.h1": "Демо, а не благодійний фонд",
    "tm.p1": "Цей сайт показує, як працюватиме Proof of Good. Він працює в пісочниці PayPal з тестовими грошима. Не вводьте дані справжньої картки: вікно PayPal тут приймає лише тестові акаунти й тестові картки.",
    "tm.p2": "Збори тут вигадані для демо. Їхні волонтери, картки й банківські виписки змодельовані та позначені як тестові.",
    "tm.p3": "ШІ-аудитор може помилятися. У справжньому запуску спершу спрацьовують жорсткі правила, як-от заморожування картки після зняття готівки, а незрозумілі випадки розглядає людина.",
    "tm.p4": "Код відкритий за ліцензією MIT на <a href='https://github.com/V1zual/proof-of-good' target='_blank' rel='noopener'>GitHub</a>.",
    // ---- shared app strings (the English text is the key) ----
    "Campaigns": "Збори", "Ledger": "Реєстр", "Volunteer portal": "Кабінет волонтера", "Try it": "Спробувати", "Home": "Головна",
    "Try the full flow": "Пройти весь шлях", "Open the menu": "Відкрити меню", "Close the menu": "Закрити меню",
    "Proof of Good · built for the PayPal AI Hackathon 2026": "Proof of Good · створено для PayPal AI Hackathon 2026",
    "PayPal sandbox, test money": "Пісочниця PayPal, тестові гроші", "Telegram bot": "Телеграм-бот", "Source": "Код",
    "Privacy": "Конфіденційність", "Terms": "Умови",
    "This page did not load": "Сторінка не завантажилася",
    "{msg}. Check your connection and {a}reload the page{z}.": "{msg}. Перевірте з'єднання й {a}оновіть сторінку{z}.",
    "{acc} spent and proven, {card} on the card, {held} held on PayPal, of a {goal} goal": "{acc} витрачено й підтверджено, {card} на картці, {held} зберігається на PayPal, ціль {goal}",
    "{raised} of {goal} raised": "{raised} з {goal} зібрано", "spent & proven": "витрачено й підтверджено", "on the card": "на картці",
    "held on PayPal": "зберігається на PayPal", "refunded": "повернуто",
    "waiting": "чекає", "held · over the goal": "на PayPal · понад ціль", "held": "на PayPal", "matches": "збігається",
    "needs a receipt": "потрібен чек", "flagged": "порушення", "top up": "поповнення",
    "active": "активний", "completed": "завершено", "frozen": "заморожено",
    "Spending frozen.": "Витрати заморожено.",
    "No more money goes to the card. The money still held on PayPal goes back to the donors.": "На картку більше не надходять гроші. Те, що ще зберігається на PayPal, повертається донорам.",
    "Receipt for the purchase": "Чек за покупку", "Photo of the purchase where it is used": "Фото покупки там, де її використовують",
    "fiscal receipt": "фіскальний чек", "demo feed": "тестова виписка",
    "{spent} of {amount} spent in checked card payments": "{spent} з {amount} витрачено перевіреними платежами карткою",
    "AI audit: {passed} of {total} checks passed": "Перевірка ШІ: пройдено {passed} з {total}",
    "Released with PayPal payout": "Виплачено через PayPal Payouts",
    "Nothing here yet": "Тут поки порожньо",
    "The first donation shows up in this list within seconds, with its PayPal id.": "Перша пожертва з'явиться в цьому списку за кілька секунд разом з її номером PayPal.",
    "Proof sent for this step": "Доказ для цього кроку",
    "Open campaigns": "Відкриті збори", "Pick a volunteer.<br>Watch every payment.": "Оберіть волонтера.<br>Стежте за платежами.",
    "Each campaign gets its money one budget line at a time, on a transparent card whose every payment is checked by AI.": "Кожен збір отримує гроші по одній статті бюджету, на прозору картку, кожен платіж з якої перевіряє ШІ.",
    "donated": "пожертвувано", "spent and proven": "витрачено й підтверджено", "refunded to donors": "повернуто донорам",
    "released to cards": "виплачено на картки", "held right now": "зберігається зараз", "card payments checked": "платежів карткою перевірено",
    "{done} of {n} budget lines spent and proven": "{done} з {n} статей бюджету витрачено й підтверджено",
    "No campaigns yet": "Зборів поки немає",
    "The demo server is setting up its example campaigns. Reload the page in a few seconds.": "Демосервер створює приклади зборів. Оновіть сторінку за кілька секунд.",
    "the money reaches the volunteer one budget line at a time": "гроші надходять волонтеру по одній статті бюджету",
    "what is still held goes back if the money is misused": "те, що ще зберігається, повертається, якщо гроші використають не за призначенням",
    "The transparent card": "Прозора картка",
    "{name} pays only with {card}. The bank reports every payment, and the AI auditor checks it the moment it happens.": "{name} платить лише карткою {card}. Банк повідомляє про кожен платіж, і ШІ-аудитор перевіряє його одразу.",
    "the campaign card": "картка збору", "No card payments yet": "Платежів карткою ще немає",
    "Each payment from the card shows up here within seconds, with the AI check next to it.": "Кожен платіж з картки з'являється тут за кілька секунд, поруч з перевіркою ШІ.",
    "Public ledger": "Публічний реєстр", "All campaigns in one table →": "Усі збори в одній таблиці →",
    "volunteer {name}": "волонтер {name}", "Where the money goes": "Куди йдуть гроші",
    "One budget line at a time goes to the card. The next one comes only after the last one is spent on the purpose and proven with a photo.": "На картку надходить одна стаття бюджету за раз. Наступна приходить лише тоді, коли попередню витрачено за призначенням і підтверджено фото.",
    "Donate": "Пожертвувати", "This campaign takes no more donations ({status}).": "Цей збір більше не приймає пожертв ({status}).",
    "Amount": "Сума", "Or any amount in USD": "Або будь-яка сума в доларах", "Enter an amount from $1 to $10,000.": "Введіть суму від $1 до $10 000.",
    "Pay with PayPal or any bank card. The money is {b}held{z} on PayPal and goes to {name}'s transparent card one budget line at a time.": "Платіть через PayPal або будь-якою банківською карткою. Гроші {b}зберігаються{z} на PayPal і надходять на прозору картку волонтера {name} по одній статті бюджету.",
    "{b}Judges and testers:{z} this is the PayPal sandbox, so no real money moves. In the PayPal window log in with the test buyer": "{b}Судді й тестувальники:{z} це пісочниця PayPal, справжні гроші не рухаються. У вікні PayPal увійдіть як тестовий покупець",
    "Test it end to end": "Перевірте весь шлях", "Donate $10.": "Пожертвуйте $10.",
    "Open the volunteer portal with the code {code}, pay with the demo card, then send a photo of any bottle of water.": "Відкрийте кабінет волонтера з кодом {code}, оплатіть тестовою карткою, а потім надішліть фото будь-якої пляшки води.",
    "Try to cheat with the card.": "Спробуйте схитрувати з карткою.", "Open the volunteer portal": "Відкрити кабінет волонтера",
    "Follow in Telegram": "Стежити в Telegram",
    "Get a message when money is released, and the photo when it is proven spent.": "Отримуйте повідомлення, коли гроші виплачено, і фото, коли витрату підтверджено.",
    "Capturing your donation…": "Зараховуємо вашу пожертву…", "Thank you": "Дякуємо",
    "{amount} is held for this campaign and reaches the volunteer only through the transparent card.": "{amount} зберігається для цього збору й дійде до волонтера лише через прозору картку.",
    "Track where your money goes →": "Стежте, куди йдуть ваші гроші →",
    "The donation was not confirmed: {msg}. Reload the page to see whether it arrived, or try again.": "Пожертву не підтверджено: {msg}. Оновіть сторінку, щоб побачити, чи вона надійшла, або спробуйте ще раз.",
    "PayPal stopped: {msg}. Try again, or reload the page.": "PayPal зупинився: {msg}. Спробуйте ще раз або оновіть сторінку.",
    "The PayPal buttons did not load. Check that nothing blocks paypal.com, then reload the page.": "Кнопки PayPal не завантажилися. Перевірте, що ніщо не блокує paypal.com, і оновіть сторінку.",
    "For volunteers": "Для волонтерів", "Spend with the card.<br>Prove with a photo.": "Платіть карткою.<br>Підтверджуйте фото.",
    "Donations reach you one budget line at a time on your transparent card. Pay only with that card and every payment is checked as it happens. Then send a photo of what you bought, and the next line comes.": "Пожертви надходять вам по одній статті бюджету на прозору картку. Платіть лише нею, і кожен платіж перевіряється одразу. Потім надішліть фото покупки, і прийде наступна стаття.",
    "Campaign code": "Код збору", "For example TRY-IT": "Наприклад, TRY-IT", "Test campaign for judges:": "Тестовий збір для суддів:",
    "others:": "інші:", "Open my campaign": "Відкрити мій збір",
    "Enter the campaign code from your volunteer invite.": "Введіть код збору з вашого запрошення волонтера.",
    "No campaign has this code. Check it and try again.": "Збору з таким кодом немає. Перевірте його і спробуйте ще раз.",
    "Photo of the item where it is used": "Фото речі там, де її використовують",
    "An original phone photo keeps its camera date": "Оригінальне фото з телефону зберігає дату зйомки",
    "Photo of the receipt": "Фото чека", "Nova Poshta, marketplace or shop receipt": "Чек Нової Пошти, маркетплейсу чи магазину",
    "Transparent card": "Прозора картка", "demo bank feed": "тестова банківська виписка", "Monobank, read only": "Monobank, лише читання",
    "left of {amount} for «{title}»": "залишилось з {amount} на «{title}»", "no budget line on the card": "на картці немає статті бюджету",
    "Frozen:": "Заморожено:", "Make the demo card pay. The bank feed reports it like a real card would:": "Оплатіть тестовою карткою. Виписка покаже це так само, як для справжньої картки:",
    "Every budget line is spent and proven.": "Усі статті бюджету витрачено й підтверджено.",
    "What to do now": "Що робити зараз", "Money arrives": "Гроші надходять", "Pay with the card": "Платіть карткою", "Send a photo": "Надішліть фото",
    "The next budget line reaches your card as soon as donors fund it.": "Наступна стаття бюджету надійде на вашу картку, щойно донори її зберуть.",
    "Buy only what the budget line is for. Every payment is checked.": "Купуйте лише те, на що призначена стаття бюджету. Кожен платіж перевіряється.",
    "A photo of the purchase in place unlocks the next line.": "Фото покупки на місці відкриває наступну статтю.",
    "not funded yet": "ще не зібрано", "being spent now": "зараз витрачається", "payments matched, photo accepted": "платежі збіглися, фото прийнято",
    "The next budget line reaches the card when {amount} is donated. {a}Donate on the public page{z}.": "Наступна стаття бюджету надійде на картку, коли буде зібрано {amount}. {a}Пожертвувати на публічній сторінці{z}.",
    "Volunteer {name} · {a}public page{z} · {b}switch campaign{z}": "Волонтер {name} · {a}публічна сторінка{z} · {b}змінити збір{z}",
    "Your campaign card": "Картка вашого збору", "Prove the budget line": "Підтвердіть статтю бюджету",
    "Nothing to prove right now": "Зараз нічого підтверджувати",
    "No budget line is on the card. When the next one arrives, its photo goes here.": "На картці немає статті бюджету. Коли надійде наступна, її фото надсилайте сюди.",
    "For «{title}»: a photo of what you bought, where it is used.": "Для «{title}»: фото покупки там, де її використовують.",
    "because the bank line does not say what was bought.": "бо з банківського рядка не видно, що купили.",
    "Photo of the item in place": "Фото речі на місці", "Receipt": "Чек", "(only for unclear payments)": "(лише для незрозумілих платежів)",
    "No photo at hand? Try a sample:": "Немає фото під рукою? Спробуйте приклад:", "Run the AI audit": "Запустити перевірку ШІ",
    "Campaign": "Збір", "Budget lines": "Статті бюджету", "Start the test over": "Почати тест заново",
    "Refunds the testers' sandbox money and clears this test campaign.": "Повертає тестувальникам гроші з пісочниці й очищує цей тестовий збір.",
    "Reset the test campaign": "Скинути тестовий збір", "Simulate: the volunteer vanished": "Симуляція: волонтер зник",
    "Closes the campaign and {b}refunds every donor's share that is still held{z} through PayPal Refunds.": "Закриває збір і {b}повертає кожному донору його частку, що ще зберігається,{z} через PayPal Refunds.",
    "Refund the held money": "Повернути гроші донорам", "Resetting…": "Скидаємо…",
    "The reset failed: {msg}. Try again in a minute.": "Не вдалося скинути: {msg}. Спробуйте за хвилину.",
    "Refund every donor's held share and close the campaign?": "Повернути кожному донору його частку й закрити збір?",
    "Refunding through PayPal…": "Повертаємо через PayPal…", "{n} failed": "{n} з помилкою",
    "Nothing was refunded: {msg}.": "Нічого не повернуто: {msg}.",
    "The bank reports the payment and the auditor checks it…": "Банк повідомляє про платіж, аудитор перевіряє…",
    "The payment was not sent: {msg}.": "Платіж не надіслано: {msg}.",
    "Add the photo of the item first. A receipt alone does not account for the budget line.": "Спочатку додайте фото речі. Сам чек не підтверджує статтю бюджету.",
    "AI auditor": "ШІ-аудитор", "{amount} released": "{amount} виплачено", "for «{title}» with PayPal Payouts": "на «{title}» через PayPal Payouts",
    "batch {id}": "пакет {id}", "Accounted for": "Підтверджено", "Rejected": "Відхилено", "Not yet": "Ще ні", "Donors see:": "Донори бачать:",
    "Next budget line on your card: {b}{amount}{z} for «{title}».": "Наступна стаття бюджету на вашій картці: {b}{amount}{z} на «{title}».",
    "Back to the card →": "Назад до картки →", "The audit did not finish": "Перевірка не завершилася",
    "{msg}. Send the photo again in a minute.": "{msg}. Надішліть фото ще раз за хвилину.",
    "Your donation": "Ваша пожертва", "Donation not found": "Пожертву не знайдено",
    "The demo server restarts now and then and forgets test donations. {a}Open the campaigns{z} to give again.": "Демосервер іноді перезапускається й забуває тестові пожертви. {a}Відкрийте збори{z}, щоб пожертвувати знову.",
    "Refunded to your PayPal": "Повернуто на ваш PayPal", "No verified proof arrived, so PayPal returned your money.": "Підтвердження не надійшло, тож PayPal повернув ваші гроші.",
    "Above the goal": "Понад ціль", "Held for the volunteer's next verified purchase, or refunded.": "Зберігається для наступної перевіреної покупки волонтера або буде повернуто.",
    "Spent from {name}'s transparent card and proven": "Витрачено з прозорої картки волонтера {name} і підтверджено",
    "On {name}'s transparent card now. Every payment from it shows up here, checked by the AI auditor.": "Зараз на прозорій картці волонтера {name}. Кожен платіж з неї з'являється тут після перевірки ШІ-аудитором.",
    "Held on PayPal. Nobody has this money yet. It goes to the card when the budget lines before it are spent and proven.": "Зберігається на PayPal. Цих грошей ще ні в кого немає. Вони надійдуть на картку, коли попередні статті бюджету витратять і підтвердять.",
    "{amount} to {title}": "{amount} на «{title}»", "Open the campaign page": "Відкрити сторінку збору", "PayPal capture": "Платіж PayPal",
    "Spending frozen:": "Витрати заморожено:", "Your held share goes back to you.": "Ваша частка, що зберігається, повертається вам.",
    "Where your money is now": "Де зараз ваші гроші", "Donations fill the budget lines in order. This is the part that is yours.": "Пожертви заповнюють статті бюджету по черзі. Ось ваша частина.",
    "The whole campaign": "Увесь збір", "Get the photo when it is spent": "Отримайте фото, коли гроші витратять",
    "Telegram sends you the proof the moment your money is released.": "Telegram надішле вам підтвердження, щойно ваші гроші виплатять.",
    "Keep this link": "Збережіть це посилання", "This page always shows what happened to your money.": "Ця сторінка завжди показує, що сталося з вашими грошима.",
    "Every dollar, in public.": "Кожен долар на виду.",
    "Each donation, release to a card, card payment, AI verdict, freeze and refund, with the real PayPal and bank ids.": "Кожна пожертва, виплата на картку, платіж карткою, вердикт ШІ, заморожування й повернення, зі справжніми номерами PayPal і банку.",
    "Search a name, an amount, a PayPal id…": "Пошук: ім'я, сума, номер PayPal…", "Search the ledger": "Пошук у реєстрі",
    "All campaigns": "Усі збори", "All events": "Усі події", "Donations": "Пожертви", "Releases to the card": "Виплати на картку",
    "Card payments": "Платежі карткою", "Freezes": "Заморожування", "Refunds": "Повернення", "AI verdicts": "Вердикти ШІ", "Proofs": "Докази",
    "Download CSV": "Завантажити CSV", "Event": "Подія",
    "Table: AG Grid Community. The bottom row sums what the filters show.": "Таблиця: AG Grid Community. Нижній рядок підсумовує те, що показують фільтри.",
    "When": "Коли", "What happened": "Що сталося", "Proof": "Доказ", "PayPal or proof id": "Номер PayPal або доказу", "Total": "Разом",
    "No events match. Clear the search or pick all events.": "Нічого не знайдено. Очистіть пошук або оберіть усі події.",
    "{n} events · donated {d} · released {r} · refunded {f}": "Подій: {n} · пожертвувано {d} · виплачено {r} · повернуто {f}",
    "Proof photo": "Фото доказу",
    "kind.donation": "пожертва", "kind.release": "виплата", "kind.card": "картка", "kind.flag": "заморожено", "kind.proof": "доказ",
    "kind.verdict": "вердикт", "kind.refund": "повернення", "kind.note": "нотатка",
    "No test donations since the last restart": "Після останнього перезапуску тестових пожертв ще не було",
    "The demo server starts clean after every update. Make the first donation and the counters for money donated, released, checked and refunded fill in within seconds.": "Демосервер стартує з чистого аркуша після кожного оновлення. Зробіть першу пожертву, і лічильники пожертвуваних, виплачених, перевірених і повернутих грошей заповняться за кілька секунд.",
    "Make the first donation": "Зробити першу пожертву",
    "The live numbers did not load ({msg}). The {a}public ledger{z} has every event.": "Живі цифри не завантажилися ({msg}). Усі події є в {a}публічному реєстрі{z}.",
    // ---- server texts known in advance: errors, audit steps, the demo campaigns ----
    "Wrong volunteer code": "Неправильний код волонтера", "No campaign with this code": "Збору з таким кодом немає",
    "Image too large (max 12 MB)": "Зображення завелике (максимум 12 МБ)", "Volunteer code needed": "Потрібен код волонтера",
    "Reading the card's bank feed": "Читаємо банківську виписку картки", "Fingerprinting the photo": "Знімаємо відбиток фото",
    "Fingerprinting the photo and the receipt": "Знімаємо відбитки фото й чека", "Looking at the photo": "Роздивляємося фото",
    "Looking at the photo and reading the receipt": "Роздивляємося фото й читаємо чек", "Weighing the evidence": "Зважуємо докази",
    "card payments": "платежі карткою", "every payment explained": "кожен платіж пояснено", "no money left the purpose": "усі гроші пішли за призначенням",
    "photo matches the purchase": "фото збігається з покупкою", "photo: real on-site photo": "фото: справжнє, з місця",
    "photo: shows the item": "фото: видно річ", "receipt matches a card payment": "чек збігається з платежем карткою",
    "receipt: looks genuine": "чек: схожий на справжній", "receipt: readable": "чек: читається", "the tranche is spent": "статтю бюджету витрачено",
    "Demo card": "Тестова картка",
    "Try it yourself: water for a shelter": "Спробуйте самі: вода для укриття",
    "A small test campaign for judges and testers. Donate $10 with the sandbox buyer and the first budget line goes to the volunteer's demo card at once. Then open the volunteer portal (code TRY-IT): make the card pay, take a photo of any bottle of water near you and send it. Try cheating too: withdraw cash or send money to another card and watch the campaign freeze.": "Невеликий тестовий збір для суддів і тестувальників. Пожертвуйте $10 від тестового покупця, і перша стаття бюджету одразу надійде на тестову картку волонтера. Потім відкрийте кабінет волонтера (код TRY-IT): оплатіть карткою, сфотографуйте будь-яку пляшку води поруч і надішліть фото. Спробуйте й схитрувати: зніміть готівку або перекажіть гроші на іншу картку й подивіться, як збір заморозиться.",
    "Bottled water for the shelter": "Питна вода для укриття", "Paper cups and napkins": "Паперові стаканчики й серветки", "Snacks for the kids": "Перекуси для дітей",
    "A generator for the maternity hospital": "Генератор для пологового будинку",
    "When the power goes out in Ivano-Frankivsk, the maternity ward switches to flashlights. A 3 kW petrol generator keeps the incubators and the delivery room running through a blackout. The money waits on PayPal and reaches the volunteer one purchase at a time. Every payment from his campaign card is visible here, and the next part is released only after the last one is proven.": "Коли в Івано-Франківську зникає світло, пологове відділення переходить на ліхтарики. Бензиновий генератор на 3 кВт тримає в роботі кувези й пологову залу під час блекауту. Гроші зберігаються на PayPal і надходять волонтеру по одній покупці. Кожен платіж з його картки збору видно тут, а наступна частина виплачується лише після підтвердження попередньої.",
    "Petrol generator Hyundai HHY 3050F": "Бензиновий генератор Hyundai HHY 3050F", "Fuel canisters and 40 l of petrol": "Каністри й 40 л бензину",
    "Delivery and installation": "Доставка й встановлення",
    "Warm winter for the school shelter": "Тепла зима для шкільного укриття",
    "School №12 turned its basement into a bomb shelter for 300 children. Three oil heaters and thermal mats mean the kids can sit through an alarm without freezing.": "Школа №12 облаштувала підвал як укриття для 300 дітей. Три масляні обігрівачі й термокилимки дозволять дітям перечекати тривогу, не замерзаючи.",
    "3 oil heaters 2.5 kW": "3 масляні обігрівачі по 2,5 кВт", "30 thermal mats": "30 термокилимків",
    "Food for the Paws animal shelter": "Корм для притулку тварин «Лапи»",
    "Eighty dogs and cats, one volunteer, winter ahead. A tonne of dry food lasts the shelter about two months.": "Вісімдесят собак і котів, один волонтер, попереду зима. Тонни сухого корму притулку вистачає приблизно на два місяці.",
    "1 000 kg of dry dog and cat food": "1 000 кг сухого корму для собак і котів", "Vet visit and vaccines": "Огляд ветеринара й вакцини",
    "Ivano-Frankivsk, Ukraine": "Івано-Франківськ, Україна", "Kharkiv, Ukraine": "Харків, Україна", "Lviv, Ukraine": "Львів, Україна",
    "Test Volunteer": "Тестовий волонтер", "Andriy K.": "Андрій К.", "Olena M.": "Олена М.", "Taras H.": "Тарас Г.",
  },
};
const DICT = I18N[LANG] || {};

// a fixed string of the site, with {name} parameters (markup can be passed as a parameter)
const L = (s, p) => {
  let out = DICT[s] ?? s;
  if (p) out = out.replace(/\{(\w+)\}/g, (m, k) => (k in p ? p[k] : m));
  return out;
};
// plural forms: English one/other, Ukrainian one/few/many
const plural = (n, en, uk) => {
  const forms = { en, uk }[LANG] || en;
  if (forms.length === 2) return forms[n === 1 ? 0 : 1];
  const m10 = n % 10, m100 = n % 100;
  return forms[m10 === 1 && m100 !== 11 ? 0 : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? 1 : 2];
};

function langSwitch() {
  return `<div class="lang" role="group" aria-label="Language">${Object.entries(LANGS).map(([k, v]) =>
    `<button type="button" data-lang="${k}" aria-pressed="${k === LANG}">${v}</button>`).join("")}</div>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-lang]");
  if (!b || b.dataset.lang === LANG) return;
  try { localStorage.setItem("lang", b.dataset.lang); } catch (er) { /* storage blocked: the browser language stays */ }
  // a ?lang= in the address would win over the pick, so it follows the pick
  const u = new URL(location.href);
  if (u.searchParams.has("lang")) { u.searchParams.set("lang", b.dataset.lang); location.replace(u); } else location.reload();
});

// static pages: <el data-i18n="key"> gets the translated HTML, <el data-i18n-attr="placeholder:key;aria-label:key"> attributes
function applyStatic(root = document) {
  root.querySelectorAll(".lang [data-lang]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === LANG));
  if (LANG === "en") return;
  root.querySelectorAll("[data-i18n]").forEach((el) => { const v = DICT[el.dataset.i18n]; if (v != null) el.innerHTML = v; });
  root.querySelectorAll("[data-i18n-attr]").forEach((el) => el.dataset.i18nAttr.split(";").forEach((pair) => {
    const [attr, key] = pair.split(":");
    if (DICT[key] != null) el.setAttribute(attr, DICT[key]);
  }));
}

// ---- live texts from the server: translated by /api/translate, remembered per language in this browser ----
const TR_KEY = "tr:" + LANG;
const TR = (() => { try { return JSON.parse(localStorage.getItem(TR_KEY) || "{}"); } catch (e) { return {}; } })();
const trTried = {};
const _e = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// server texts built from a template (card labels, audit check names): translated by pattern, no model needed
const PATTERNS = LANG === "uk" ? [
  [/^Demo card\b/, "Тестова картка"], [/^card: /, "картка: "], [/^receipt explains «(.+)»$/, "чек пояснює «$1»"],
  [/^(photo|receipt): (unique file|not reused|taken after the money was released|capture date|not edited|content credentials)$/,
    (m, what, check) => `${what === "photo" ? "фото" : "чек"}: ${{ "unique file": "унікальний файл", "not reused": "не використаний раніше",
      "taken after the money was released": "зроблений після виплати", "capture date": "дата зйомки", "not edited": "без редагування",
      "content credentials": "мітки походження C2PA" }[check]}`],
] : [];
const byPattern = (s) => { for (const [re, to] of PATTERNS) if (re.test(s)) return s.replace(re, to); return null; };
// as text: the known translation, else the English original
const tr = (s) => { s = String(s ?? ""); return LANG === "en" ? s : DICT[s] ?? TR[s] ?? byPattern(s) ?? s; };
// as HTML: when the translation is not known yet, a marked span that is filled in when it arrives
const dyn = (s) => {
  s = String(s ?? "");
  if (LANG === "en" || !s.trim() || DICT[s] != null || TR[s] != null || byPattern(s) != null) return _e(tr(s));
  return `<span data-tr="${_e(s)}">${_e(s)}</span>`;
};
async function translateTexts(texts) {
  const now = Date.now();
  const missing = [...new Set(texts.map(String))].filter((s) => s.trim() && DICT[s] == null && TR[s] == null && !(now - (trTried[s] || 0) < 60000)).slice(0, 60);
  if (LANG === "en" || !missing.length) return false;
  missing.forEach((s) => (trTried[s] = now));
  try {
    const r = await fetch("/api/translate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: LANG, texts: missing }) });
    if (!r.ok) return false;
    const got = await r.json();
    Object.assign(TR, got);
    try {
      const keys = Object.keys(TR);
      if (keys.length > 1500) keys.slice(0, 500).forEach((k) => delete TR[k]);
      localStorage.setItem(TR_KEY, JSON.stringify(TR));
    } catch (e) { /* storage full or blocked: translations stay for this visit */ }
    return Object.keys(got).length > 0;
  } catch (e) { return false; }
}
function fillTranslated(root = document) {
  root.querySelectorAll("[data-tr]").forEach((el) => {
    const v = TR[el.dataset.tr];
    if (v != null) { el.textContent = v; el.removeAttribute("data-tr"); }
  });
}
let trTimer = 0;
function translatePage() {
  clearTimeout(trTimer);
  trTimer = setTimeout(async () => {
    fillTranslated();
    const pending = [...document.querySelectorAll("[data-tr]")].map((el) => el.dataset.tr);
    if (await translateTexts(pending)) fillTranslated();
  }, 150);
}
if (LANG !== "en") new MutationObserver(translatePage).observe(document.documentElement, { childList: true, subtree: true });

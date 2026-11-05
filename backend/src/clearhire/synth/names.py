"""Fictional people, companies and places for the synthetic dataset. Any resemblance is coincidental."""

from __future__ import annotations

RU_MALE = """Александр Алексей Андрей Антон Артём Борис Вадим Валентин Василий Виктор Владимир Глеб Григорий
Даниил Денис Дмитрий Евгений Егор Иван Игорь Илья Кирилл Константин Леонид Максим Михаил Никита Николай
Олег Павел Роман Руслан Сергей Степан Тимур Фёдор Юрий Ярослав""".split()

RU_FEMALE = """Алина Алёна Алиса Анастасия Анна Валерия Варвара Вера Вероника Виктория Дарья Евгения Екатерина
Елена Елизавета Ирина Карина Кристина Ксения Любовь Маргарита Марина Мария Надежда Наталья Ольга Полина
Светлана София Татьяна Ульяна Юлия Яна""".split()

# masculine forms; feminine forms are derived by feminine_surname()
RU_SURNAMES = """Абрамов Алексеев Белов Беляев Волков Воробьёв Гаврилов Громов Гусев Давыдов Егоров Жуков Зайцев
Захаров Иванов Ильин Калинин Киселёв Ковалёв Козлов Комаров Кузнецов Лебедев Макаров Медведев Морозов
Новиков Орлов Павлов Петров Попов Романов Семёнов Смирнов Соколов Соловьёв Сорокин Тарасов Фролов
Яковлев Островский Покровский Вишневский""".split()

EN_MALE = """Adam Alex Andrew Ben Chris Daniel David Ethan George Henry Jack James Jonathan Liam Lucas Mark
Matthew Michael Nathan Oliver Peter Ryan Samuel Thomas William""".split()
EN_FEMALE = """Amelia Anna Charlotte Chloe Claire Emily Emma Grace Hannah Isabella Jessica Julia Kate Laura
Lucy Mia Natalie Olivia Rachel Rebecca Sarah Sophie Zoe""".split()
EN_SURNAMES = """Adams Baker Bennett Brooks Carter Clarke Collins Cooper Davies Edwards Evans Fisher Foster
Graham Green Hall Harris Hughes Jackson Kelly King Lewis Martin Mitchell Morgan Murphy Parker Phillips
Reed Roberts Scott Taylor Turner Walker Ward Watson White Wood Wright""".split()

# international names for English-language CVs: (first male, first female, surnames)
WORLD: list[tuple[list[str], list[str], list[str]]] = [
    (["Ahmed", "Omar", "Youssef", "Khalid", "Hassan"], ["Fatima", "Layla", "Mariam", "Noor", "Sara"],
     ["Al-Rashid", "Haddad", "Mansour", "Nasser", "Saleh"]),
    (["Wei", "Jun", "Hao", "Lei", "Ming"], ["Li", "Mei", "Xin", "Yan", "Ying"],
     ["Chen", "Wang", "Zhang", "Liu", "Zhao"]),
    (["Arjun", "Rahul", "Vikram", "Rohan", "Karan"], ["Priya", "Ananya", "Neha", "Pooja", "Divya"],
     ["Sharma", "Patel", "Gupta", "Iyer", "Reddy"]),
    (["Timur", "Rustam", "Bakhtiyar", "Azamat", "Daniyar"], ["Aigerim", "Dilnoza", "Madina", "Zarina", "Kamila"],
     ["Nurlanov", "Karimov", "Abdullaev", "Tursunov", "Seitkali"]),
    (["Lucas", "Mateo", "Diego", "Javier", "Pablo"], ["Lucia", "Sofia", "Valentina", "Elena", "Camila"],
     ["Garcia", "Martinez", "Lopez", "Fernandez", "Silva"]),
]  # fmt: skip

RU_COMPANIES = [
    "ООО «Северный ветер»", "ООО «Тесла Логистик»", "АО «Квант Софт»", "ООО «Ромашка Диджитал»",
    "ООО «Ладога Тех»", "ООО «Синяя птица»", "АО «Перспектива»", "ООО «Цифровой Двор»", "ООО «Байкал Системс»",
    "ООО «Альфа Ритейл Тех»", "ООО «Медведь Лабс»", "ООО «Город Решений»", "ООО «Волна Финтех»",
    "ООО «Кедр Аналитика»", "ООО «Маяк Медиа»",
]  # fmt: skip
EN_COMPANIES = [
    "Northwind Labs", "Bluefin Analytics", "Copperleaf Software", "Harbor Freight Tech", "Lumio Health",
    "Nimbus Payments", "Orchard Retail Systems", "Pinecrest Logistics", "Quartz Media", "Redwood Fintech",
    "Silverline Games", "Tidewater Insurance Tech", "Vertex Mobility", "Willow Education", "Zephyr Cloud",
]  # fmt: skip

RU_UNIVERSITIES = [
    "МГУ им. М. В. Ломоносова", "МГТУ им. Н. Э. Баумана", "МФТИ", "НИУ ВШЭ", "НИТУ МИСИС", "ИТМО",
    "СПбГУ", "УрФУ", "НГУ", "Казанский федеральный университет",
]  # fmt: skip
EN_UNIVERSITIES = [
    "University of Manchester", "Technical University of Munich", "University of Toronto", "Delft University of Technology",
    "Nanyang Technological University", "University of Edinburgh", "KTH Royal Institute of Technology",
    "Higher School of Economics", "Bauman Moscow State Technical University", "University of Belgrade",
]  # fmt: skip
RU_CITIES = [
    "Москва",
    "Санкт-Петербург",
    "Казань",
    "Новосибирск",
    "Екатеринбург",
    "Нижний Новгород",
    "Самара",
]
EN_CITIES = [
    "Moscow",
    "Saint Petersburg",
    "Belgrade",
    "Almaty",
    "Tashkent",
    "Yerevan",
    "Dubai",
    "Berlin",
    "Remote",
]


def feminine_surname(surname: str) -> str:
    if surname.endswith(("ов", "ёв", "ев", "ин")):
        return surname + "а"
    if surname.endswith("ский"):
        return surname[:-2] + "ая"
    return surname

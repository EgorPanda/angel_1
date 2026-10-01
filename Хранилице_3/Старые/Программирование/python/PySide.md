Преобразование файлов

```
pyside6-rcc имя файла.qrc -o имя файла.py
pyside6-uic имя файла.ui -o имя файла.py
```


настройка стилей

```
Цвет фона
background-color: rgba(255,255,255,0);

границы
border: 0px solid rgba(255,255,255,0);

Скругление
border-radius: 5px;

Скругление одного угла
border-bottom-right-radius: 5px


Тип шрифта
font-weight: bolt

Размер шрифта
font-size: 20 pt

отcтуп (сперху(top))
padding-top: 10 px
```

настройка стилей кнопок

```
Обычное состояние кнопки
QPushButton{свойства}

наведение на кнопку
QPushButton:hover{свойства}

Нажатие на кнопку
QPushButton:pressed{свойства}
```

Настройка стилей таблицы (table view)

```
Для всей таблицы
QTableView{свойства}

Для колонок
QTableView::section{свойства}

Для ячейки
QTableView::item{свойства}

Для выбранной ячейки
QTableView::item:selected{свойства}
```

настрйки

```
placeholderText - текст лоя подскащки при введение текста

```

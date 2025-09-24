# ui/styles.py
STYLESHEET = """
/* Основные стили */
QMainWindow {
    background-color: #0A0A0A;
    color: #FFFFFF;
}

QWidget {
    background-color: #0A0A0A;
    color: #FFFFFF;
}

/* Группы */
QGroupBox {
    color: #F5F5F5;
    font-weight: bold;
    border: 1px solid #333333;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    background-color: #151515;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 3px 10px;
    background-color: #1B365D;
    color: #F5F5F5;
    border-radius: 4px;
    font-size: 11px;
}

/* Текстовые поля */
QLineEdit {
    background-color: #252525;
    color: #CCCCCC;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 6px;
    font-size: 12px;
}

QLineEdit:focus {
    border: 1px solid #003DA5;
    background-color: #2A2A2A;
}

QTextEdit {
    background-color: #151515;
    color: #CCCCCC;
    border: 1px solid #333333;
    border-radius: 4px;
    font-family: 'Courier New', monospace;
    font-size: 10px;
    padding: 5px;
}

/* Кнопки */
QPushButton {
    background-color: #1B365D;
    color: #F5F5F5;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
    min-width: 90px;
    font-size: 11px;
}

QPushButton:hover {
    background-color: #003DA5;
    border: 1px solid #C0C0C0;
}

QPushButton:pressed {
    background-color: #7A0C21;
    border: 1px solid #F5F5F5;
}

QPushButton:disabled {
    background-color: #252525;
    color: #666666;
    border: 1px solid #333333;
}

/* Статус бар */
QStatusBar {
    background-color: #1A1A1A;
    color: #CCCCCC;
    border-top: 1px solid #333333;
    font-size: 10px;
}

QStatusBar::item {
    border: none;
}

/* Labels */
QLabel {
    color: #CCCCCC;
    font-size: 12px;
    font-weight: normal;
}

/* Скроллбары */
QScrollBar:vertical {
    background-color: #1A1A1A;
    width: 12px;
    border-radius: 6px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #404040;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #606060;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}

/* Меню */
QMenu {
    background-color: #1A1A1A;
    color: #CCCCCC;
    border: 1px solid #333333;
    border-radius: 4px;
}

QMenu::item {
    background-color: transparent;
    padding: 6px 24px;
    font-size: 11px;
}

QMenu::item:selected {
    background-color: #003DA5;
    color: #F5F5F5;
}

QMenu::item:disabled {
    color: #666666;
}

/* Тултипы */
QToolTip {
    background-color: #1B365D;
    color: #F5F5F5;
    border: 1px solid #333333;
    border-radius: 3px;
    padding: 6px;
    font-size: 10px;
}

/* Разделители */
QFrame[frameShape="4"] { /* HLine */
    background-color: #333333;
    border: none;
    height: 1px;
}
"""
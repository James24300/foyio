from PySide6.QtCore import Qt, QAbstractTableModel
from utils.formatters import format_money
from utils.theme import THEME

class TransactionsModel(QAbstractTableModel):

    headers = ["Date", "Type", "Montant", "Catégorie", "Description"]

    def __init__(self, transactions, categories):
        super().__init__()
        self.transactions = transactions
        self.categories = categories

    def rowCount(self, parent=None):
        return len(self.transactions)

    def columnCount(self, parent=None):
        return 5

    def data(self, index, role):

        if not index.isValid():
            return None

        transaction = self.transactions[index.row()]
        column = index.column()

        if role == Qt.DisplayRole:

            if column == 0:
                return transaction.date.strftime("%d/%m/%Y")

            elif column == 1:
                return "Revenu" if transaction.type == "income" else "Dépense"

            elif column == 2:
                return format_money(transaction.amount)

            elif column == 3:
                category = self.categories.get(transaction.category_id)
                if category:
                    return category.name   # nom seul, sans le fichier icône
                return "Inconnu"

            elif column == 4:
                return transaction.note or ""

    def headerData(self, section, orientation, role):

        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]

        return None
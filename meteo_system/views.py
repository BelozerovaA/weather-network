"""View: консольное представление."""
class ConsoleView:
    def header(self, text):
        print(f"\n--- {text} ---")

    def line(self, text):
        print(text)

    def error(self, text):
        print(f"Ошибка: {text}")

from app.rag.symbol_extractor import extract_symbol_metadata


source = """
class Calculator:
    def divide(self, a: int, b: int) -> float:
        return a / b
"""

for symbol in extract_symbol_metadata(source, "calculator.py"):
    print(symbol)

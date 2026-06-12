"""Build samples/sample_submissions.zip: three fake students for rubric_python.csv.

alice_smith - perfect submission
bob_jones   - partial (no calculate_average, short README, no math import)
carol_wu    - empty folder
"""
from pathlib import Path
import zipfile

ALICE_MAIN = '''"""Average calculator assignment."""
import math


def calculate_average(numbers):
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def main():
    data = [2, 4, 6, 8]
    print("average:", calculate_average(data))
    print("sqrt of 16:", math.sqrt(16))


if __name__ == "__main__":
    main()
'''

ALICE_README = """# Average Calculator

This program computes the average of a list of numbers using a dedicated
calculate_average function. I tested it with empty lists, single values, and
mixed integers to make sure division by zero never happens. The math module
is used to demonstrate square roots in the demo output. Run the program with
python main.py and it prints the average of the sample data set.
"""

BOB_MAIN = '''def average(numbers):
    return sum(numbers) / len(numbers)


print("average:", average([1, 2, 3]))
'''

BOB_README = "My homework. It computes an average of some numbers.\n"


def main() -> None:
    out = Path(__file__).parent / "sample_submissions.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("alice_smith/main.py", ALICE_MAIN)
        zf.writestr("alice_smith/README.md", ALICE_README)
        zf.writestr("bob_jones/main.py", BOB_MAIN)
        zf.writestr("bob_jones/README.md", BOB_README)
        zf.writestr("carol_wu/", "")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

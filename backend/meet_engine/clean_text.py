import re


def clean_markdown(text):

    if not text:
        return ""

    # remove extra spaces
    text = re.sub(r"[ \t]+", " ", text)

    # fix broken hyphenated words
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # replace line breaks with spaces
    text = text.replace("\n", " ")

    # remove multiple spaces
    text = re.sub(r"\s+", " ", text)

    return text.strip()
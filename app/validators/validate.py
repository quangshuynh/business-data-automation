import re
import pandas as pd


EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)


def validate_required_columns(df, required_columns, dataset_name):
    """
    validates that all required columns exist in the dataframe
    :param df: dataframe to validate
    :param required_columns: columns required in the dataframe
    :param dataset_name: name of the dataset
    :returns: none
    """
    missing = [col for col in required_columns if col not in df.columns]

    if missing:
        raise ValueError( f"{dataset_name} is missing required columns: {missing}" )


def validate_unique_ids(df, id_column, dataset_name):
    """
    validates that all ids in the specified column are unique
    :param df: dataframe to validate
    :param id_column: column containing ids
    :param dataset_name: name of the dataset
    :returns: none
    """
    duplicates = df[df[id_column].duplicated(keep=False)]

    if not duplicates.empty:
        duplicate_ids = duplicates[id_column].tolist()

        raise ValueError(
            f"{dataset_name} contains duplicate {id_column} values: "
            f"{duplicate_ids}"
        )


def normalize_email(email):
    """
    normalizes an email address by removing whitespace and converting to lowercase
    :param email: email address to normalize
    :returns: normalized email address or none
    """
    if pd.isna(email):
        return None

    return str(email).strip().lower()


def is_valid_email(email):
    """
    checks whether an email address matches the expected format
    :param email: email address to validate
    :returns: true if the email is valid otherwise false
    """
    if email is None:
        return False
    return bool(EMAIL_PATTERN.match(email))


def normalize_phone(phone):
    """
    normalizes a phone number into a standard ten digit format
    :param phone: phone number to normalize
    :returns: formatted phone number or none
    """
    if pd.isna(phone):
        return None

    digits = re.sub(r"\D", "", str(phone))

    if len(digits) == 10:
        return (
            f"({digits[:3]}) " #(555)
            f"{digits[3:6]}-"  #555-
            f"{digits[6:]}"    #5555
        )

    return None


def validate_positive_amounts(df, column_name, dataset_name):
    """
    validates that values in the specified column are not negative
    :param df: dataframe to validate
    :param column_name: column containing amounts
    :param dataset_name: name of the dataset
    :returns: none
    """
    invalid = df[df[column_name] < 0]

    if not invalid.empty:
        raise ValueError( f"{dataset_name} contains negative values in {column_name}" )
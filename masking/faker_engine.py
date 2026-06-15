from __future__ import annotations

import logging

from faker import Faker

from masking.recognizer import PIIEntity

logger = logging.getLogger(__name__)


class PIIFakerEngine:
    def __init__(self, locale: str = "en_US") -> None:
        # Initialize Faker with optional locale
        self.faker = Faker(locale)

        # Stateful inventory tracking to keep text masks deterministic across chunks/pages
        self.global_mapping: dict[str, str] = {}

        self.entity_types: dict[str, str] = {}

        # Map Presidio/NER entity types directly to Faker generation methods
        self.provider_map = {
            # --- STANDARD NAMES & DEMOGRAPHICS ---
            "PERSON": self.faker.name,
            "GIVENNAME": self.faker.first_name,
            "MIDDLENAME": self.faker.first_name,
            "LASTNAME": self.faker.last_name,
            "USERNAME": self.faker.user_name,
            "TITLE": self.faker.prefix,  # e.g., Mr., Dr., Mrs.
            "AGE": lambda: str(self.faker.random_int(min=18, max=90)),
            "GENDER": lambda: self.faker.random_element(
                elements=("Male", "Female", "Non-binary", "Other")
            ),
            "SEX": lambda: self.faker.random_element(elements=("M", "F", "X")),
            "NATIONALITY": self.faker.country,
            "BLOODTYPE": lambda: self.faker.random_element(
                elements=("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
            ),
            "JOBTITLE": self.faker.job,
            "PROFESSION": self.faker.job,
            "MARITALSTATUS": lambda: self.faker.random_element(
                elements=("Single", "Married", "Divorced", "Widowed")
            ),
            # --- CONTACT & ONLINE ---
            "EMAIL_ADDRESS": self.faker.company_email,
            "EMAIL": self.faker.company_email,
            "PHONE_NUMBER": self.faker.phone_number,
            "PHONENUMBER": self.faker.phone_number,
            "TEL": self.faker.phone_number,
            "IP_ADDRESS": self.faker.ipv4,
            "IPV4": self.faker.ipv4,
            "IPV6": self.faker.ipv6,
            "MAC": self.faker.mac_address,
            "IMEI": lambda: self.faker.imei(),  # Mobile device identifier
            "URL": self.faker.url,
            "PASSWORD": self.faker.password,
            # --- ORGANIZATIONS & LOCATIONS ---
            "ORGANIZATION": self.faker.company,
            "COMPANYNAME": self.faker.company,
            "LOCATION": self.faker.city,
            "CITY": self.faker.city,
            "STATE": self.faker.state,
            "COUNTRY": self.faker.country,
            "STREET": self.faker.street_address,
            "SECONDARYADDRESS": self.faker.secondary_address,  # Apt/Suite numbers
            "BUILDINGNUMBER": self.faker.building_number,
            "ZIPCODE": self.faker.postcode,
            "POSTCODE": self.faker.postcode,
            # --- FINANCIAL ---
            "IBAN_CODE": self.faker.iban,
            "US_BANK_NUMBER": lambda: self.faker.numerify(text="ACCT-#######"),
            "ACCOUNTNUMBER": self.faker.bban,
            "ROUTINGNUMBER": self.faker.aba,  # US Bank Routing Number
            "SWIFT": self.faker.swift,  # International Bank Code
            "SWIFTCODE": self.faker.swift,
            "CREDIT_CARD": self.faker.credit_card_number,
            "CREDITCARDNUMBER": self.faker.credit_card_number,
            "AMOUNT": lambda: str(self.faker.random_number(digits=4)),
            "CURRENCYSYMBOL": self.faker.currency_symbol,
            "TAXNUMBER": lambda: self.faker.bothify(text="??-#######"),
            # --- TEMPORAL (Dates & Times) ---
            "DATE": lambda: self.faker.date_this_century().strftime("%Y-%m-%d"),
            "DATE_TIME": lambda: self.faker.date_this_decade().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "DOB": lambda: self.faker.date_of_birth().strftime("%Y-%m-%d"),
            "TIME": self.faker.time,
            "YEAR": self.faker.year,
            # --- GOVERNMENT IDs & VEHICLES ---
            "US_SSN": self.faker.ssn,
            "IDCARD": lambda: self.faker.bothify(
                text="??#######", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            ),
            "DRIVERLICENSE": lambda: self.faker.bothify(
                text="?#######", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            ),
            "PASSPORT": lambda: self.faker.bothify(
                text="??#######", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            ),
            "LICENSEPLATE": self.faker.license_plate,
            "VEHICLEVIN": self.faker.vin,
            # --- HEALTHCARE & CATCH-ALL ---
            "DISEASE": lambda: (
                f"COND-{self.faker.lexify(text='????', letters='ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"
            ),
            "MEDICATION": lambda: (
                f"MED-{self.faker.lexify(text='????', letters='ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"
            ),
            "MISC": lambda: (
                f"MISC-{self.faker.lexify(text='??????', letters='ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"
            ),
            "O": lambda: f"REF-{self.faker.lexify(text='????-????')}",
        }

    def _generate_fake_value(self, entity_type: str, original_text: str) -> str:
        """
        Returns a consistent, highly realistic fake value for a given original string sequence.
        """
        cleaned_key = original_text.strip().lower()

        # 1. Return existing fake value if we've seen this exact entity before
        if cleaned_key in self.global_mapping:
            return self.global_mapping[cleaned_key]

        # 2. Generate a new realistic value based on the recognized type
        # If the type isn't in our map, fallback to a generic alphanumeric string
        generator = self.provider_map.get(
            entity_type, lambda: f"REF-{self.faker.lexify(text='????-????')}"
        )

        fake_value = str(generator())

        # 3. Store in dictionary to maintain global document consistency
        self.global_mapping[cleaned_key] = fake_value

        self.entity_types[cleaned_key] = entity_type

        return fake_value

    def mask_text(self, text: str, entities: list[PIIEntity]) -> str:
        """
        Substitutes discovered sensitive words with realistic Faker entities.
        Processes items in reverse alignment order to prevent character displacement loops.
        """
        if not entities:
            return text

        # CRITICAL: Sort from tail to head to isolate downstream index shifting
        reverse_sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)
        modified_text = text

        for entity in reverse_sorted_entities:
            fake_placeholder = self._generate_fake_value(
                entity.entity_type, entity.text
            )

            # Splice the realistic fake value cleanly into the markdown layer
            modified_text = (
                modified_text[: entity.start]
                + fake_placeholder
                + modified_text[entity.end :]
            )

        return modified_text

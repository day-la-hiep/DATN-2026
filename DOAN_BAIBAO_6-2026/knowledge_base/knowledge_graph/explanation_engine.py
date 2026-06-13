import os
import json


class ExplanationEngine:

    def __init__(self, knowledge_dir):

        self.disease_db = {}

        self.load_knowledge(
            knowledge_dir
        )

    def load_knowledge(
        self,
        knowledge_dir
    ):

        for file_name in os.listdir(
            knowledge_dir
        ):

            if not file_name.endswith(
                ".json"
            ):
                continue

            file_path = os.path.join(
                knowledge_dir,
                file_name
            )

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

                disease_id = data[
                    "metadata"
                ][
                    "disease_id"
                ]

                self.disease_db[
                    disease_id
                ] = data

    def generate(
        self,
        disease_id,
        disease_score,
        reasoning_details
    ):

        disease = self.disease_db[
            disease_id
        ]

        matched_features = []

        for item in reasoning_details:

            matched_features.append(
                item["feature"]
            )

        metadata = disease.get("metadata", {})
        etiology = disease.get("etiology", {})
        clinical_features = disease.get("clinical_features", {})
        treatment = disease.get("treatment", {})

        return {

            "disease_id":
                disease_id,

            "disease_name":
                metadata.get("disease_name", disease_id),

            "severity":
                metadata.get("severity", "Unknown"),

            "score":
                round(
                    disease_score,
                    2
                ),

            "matched_features":
                matched_features,

            "risk_factors":
                etiology.get("risk_factors", []),

            "symptoms":
                clinical_features.get("symptoms", []),

            "common_locations":
                clinical_features.get("common_locations", []),

            "first_line_treatment":
                treatment.get("first_line", []),

            "complications":
                disease.get("complications", [])
        }

    def display(
        self,
        explanation
    ):

        print("=" * 60)
        print("LIKELY DISEASE")
        print("=" * 60)

        print(
            explanation[
                "disease_name"
            ]
        )

        print(
            f"\nScore: "
            f"{explanation['score']}"
        )

        print(
            f"\nSeverity: "
            f"{explanation['severity']}"
        )

        print("\nMatched Features")

        for feature in explanation[
            "matched_features"
        ]:

            print(
                f"- {feature}"
            )

        print("\nRisk Factors")

        for risk in explanation[
            "risk_factors"
        ]:

            print(
                f"- {risk}"
            )

        print("\nSymptoms")

        for symptom in explanation[
            "symptoms"
        ]:

            print(
                f"- {symptom}"
            )

        print("\nCommon Locations")

        for location in explanation[
            "common_locations"
        ]:

            print(
                f"- {location}"
            )

        print(
            "\nFirst Line Treatment"
        )

        for treatment in explanation[
            "first_line_treatment"
        ]:

            print(
                f"- {treatment}"
            )

        print("\nComplications")

        for complication in explanation[
            "complications"
        ]:

            print(
                f"- {complication}"
            )
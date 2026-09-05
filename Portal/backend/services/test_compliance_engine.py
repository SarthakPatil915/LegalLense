from backend.services.compliance_engine import ComplianceEngine


def ocr(**overrides):
    fields = {
        "manufacturer_packer_importer_details": {"value": "ABC Foods, Pune", "detected": True, "confidence": 0.98},
        "country_of_origin": {"value": "India", "detected": True, "confidence": 0.98},
        "common_generic_name_of_commodity": {"value": "Rice", "detected": True, "confidence": 0.98},
        "net_quantity": {"value": "5 kg", "detected": True, "confidence": 0.98},
        "month_and_year_of_manufacture_or_packing": {"value": "08/2026", "detected": True, "confidence": 0.98},
        "maximum_retail_price_mrp": {"value": "MRP Rs. 450", "detected": True, "confidence": 0.98},
        "unit_sale_price": {"value": "Rs. 90/kg", "detected": True, "confidence": 0.98},
        "consumer_care_details": {"value": {"name": "ABC", "address": "Pune", "telephone_number": "1800123456", "email_address": "care@abc.example"}, "detected": True, "confidence": 0.98},
    }
    result = {"document_id": "DOC-TEST", "product_type": "packaged_commodity", "package_type": "retail", "full_text": "", "fields": fields}
    result.update(overrides)
    return result


def test_fully_compliant_retail_package():
    assert ComplianceEngine().evaluate(ocr(), "e_commerce_product_listing").overall_status == "COMPLIANT"


def test_missing_mrp_is_non_compliant():
    data = ocr()
    del data["fields"]["maximum_retail_price_mrp"]
    assert ComplianceEngine().evaluate(data, "e_commerce_product_listing").overall_status == "NON_COMPLIANT"


def test_ocr_mrp_without_currency_is_detected():
    data = ocr(full_text="MRP: 149\nConsumer Care: 1800-123-4567\nEmail: care@example.com")
    data["fields"] = {}
    data["detections"] = [{"confidence": 0.98}]
    result = ComplianceEngine().evaluate(data, "e_commerce_product_listing")
    mrp = result.rule_results[0].required_fields["maximum_retail_price_mrp"]
    assert mrp.status == "PASS"
    assert mrp.value["normalized_value"] == 149


def test_ocr_consumer_care_reads_email_on_next_line():
    data = ocr(full_text="MRP: Rs. 149\nConsumer Care: 1800-123-4567\nEmail: care@example.com")
    data["fields"] = {}
    data["detections"] = [{"confidence": 0.98}]
    result = ComplianceEngine().evaluate(data, "e_commerce_product_listing")
    care = result.rule_results[0].required_fields["consumer_care_details"]
    assert care.value["telephone_number"] == "1800-123-4567"
    assert care.value["email_address"] == "care@example.com"


def test_missing_consumer_email_is_partial():
    data = ocr()
    data["fields"]["consumer_care_details"]["value"]["email_address"] = None
    assert ComplianceEngine().evaluate(data, "e_commerce_product_listing").overall_status == "PARTIALLY_COMPLIANT"


def test_wholesale_profile_evaluates_wholesale_rule():
    result = ComplianceEngine().evaluate(ocr(package_type="wholesale"), "wholesale_package")
    assert result.rule_results[0].rule_id == "LMPC-R24-WHOLESALE-DECLARATIONS"


def test_low_confidence_requires_manual_verification():
    data = ocr()
    data["fields"]["country_of_origin"]["confidence"] = 0.4
    assert ComplianceEngine().evaluate(data, "e_commerce_product_listing").overall_status == "NEEDS_MANUAL_VERIFICATION"


def test_expired_instrument_is_non_compliant():
    data = {"document_id": "INST-1", "product_type": "weighing_instrument", "fields": {}, "instrument_category": "weighing_instrument", "last_verification_date": "2020-08-20"}
    assert ComplianceEngine().evaluate(data, "pos_hardware_audit").overall_status == "NON_COMPLIANT"


def test_missing_physical_seal_requires_manual_verification():
    data = {"document_id": "INST-2", "product_type": "weighing_instrument", "fields": {}, "instrument_category": "weighing_instrument", "last_verification_date": "2026-08-20"}
    result = ComplianceEngine().evaluate(data, "pos_hardware_audit")
    assert result.rule_results[1].status == "NEEDS_MANUAL_VERIFICATION"


def test_unrelated_product_is_not_applicable():
    data = ocr(product_type="unrelated")
    assert ComplianceEngine().evaluate(data, "e_commerce_product_listing").overall_status == "NOT_APPLICABLE"
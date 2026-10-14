"""Run: venv/bin/python -m unittest discover -s tests"""

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal as D

from app.services import billing_calc as bc


class FlatBillTest(unittest.TestCase):
    def test_spec_example(self):
        # Billing Flow PDF: 100 kWh, MSEB ₹11.20/unit after taxes → ₹1,120 + ₹150 + GST ₹27 = ₹1,297
        b = bc.calculate_flat_bill(D("100"), tariff=D("9.50"), eff_rate=D("11.20"), indram_rate=D("1.50"))
        self.assertEqual(b["electricity_charges_incl_tax"], D("1120.00"))
        self.assertEqual(b["indram_charges"], D("150.00"))
        self.assertEqual(b["indram_cgst"] + b["indram_sgst"], D("27.00"))
        self.assertEqual(b["indram_total"], D("177.00"))           # ₹1.77 per unit
        self.assertEqual(b["total_payable"], D("1297.00"))
        self.assertEqual(b["bill_excl_taxes"], D("950.00"))
        self.assertEqual(b["mseb_taxes"], D("170.00"))

    def test_parts_add_up_with_rounding(self):
        b = bc.calculate_flat_bill(D("37.4567"), D("8.1234"), D("10.9876"), D("1.75"))
        self.assertEqual(b["bill_excl_taxes"] + b["mseb_taxes"], b["electricity_charges_incl_tax"])
        self.assertEqual(b["indram_charges"] + b["indram_cgst"] + b["indram_sgst"], b["indram_total"])
        self.assertEqual(b["electricity_charges_incl_tax"] + b["indram_total"], b["total_payable"])

    def test_zero_units(self):
        self.assertEqual(bc.calculate_flat_bill(D("0"), D("9"), D("11"), D("1.5"))["total_payable"], D("0"))

    def test_effective_rate(self):
        self.assertEqual(bc.effective_rate(D("11200"), D("1000")), D("11.2000"))
        with self.assertRaises(ValueError):
            bc.effective_rate(D("100"), D("0"))


class LateFeeTest(unittest.TestCase):
    def test_resident_late_fee_no_gst(self):
        self.assertEqual(bc.late_fee(D("1297.00"), D("5")), D("64.85"))

    def test_allowed_after_due_date_plus_grace(self):
        self.assertEqual(bc.late_fee_allowed_from(date(2026, 11, 10), 0), date(2026, 11, 11))
        self.assertEqual(bc.late_fee_allowed_from(date(2026, 11, 10), 7), date(2026, 11, 18))


class IndramInvoiceTest(unittest.TestCase):
    def test_without_late_fee(self):
        inv = bc.calculate_indram_invoice(D("150.00"))
        self.assertEqual((inv["late_fee"], inv["cgst"], inv["sgst"], inv["rounding"], inv["total_payable"]),
                         (D("0.00"), D("13.50"), D("13.50"), D("0.00"), D("177.00")))

    def test_gst_on_charges_plus_late_fee(self):
        inv = bc.calculate_indram_invoice(D("1000.00"), late_fee_pct=D("5"))
        self.assertEqual(inv["late_fee"], D("50.00"))
        self.assertEqual(inv["cgst"], D("94.50"))                   # 9% of 1000 + 9% of 50
        self.assertEqual(inv["total_payable"], D("1239.00"))

    def test_rounds_to_rupee_like_sample_invoice(self):
        # INV-000001: 1 kWh x 1.50 → CGST 0.14 + SGST 0.14, rounding 0.22, total 2.00
        inv = bc.calculate_indram_invoice(D("1.50"))
        self.assertEqual((inv["cgst"], inv["sgst"], inv["rounding"], inv["total_payable"]),
                         (D("0.14"), D("0.14"), D("0.22"), D("2.00")))
        self.assertEqual(bc.calculate_indram_invoice(D("17.00"))["rounding"], D("-0.06"))   # 20.06 → 20.00
        self.assertEqual(bc.amount_in_words(D("2.00"), "Indian Rupee"), "Indian Rupee Two Only")

    def test_numbers(self):
        self.assertEqual(bc.financial_year(date(2026, 10, 14)), "2026-27")
        self.assertEqual(bc.financial_year(date(2027, 3, 31)), "2026-27")
        self.assertEqual(bc.financial_year(date(2027, 4, 1)), "2027-28")
        self.assertEqual(bc.financial_year(date(2099, 6, 1)), "2099-00")
        self.assertEqual(bc.format_invoice_number("2026-27", 1), "IND/2026-27/0001")
        self.assertEqual(bc.format_bill_number(12, 45), "SOC12-000045")


class PeriodTest(unittest.TestCase):
    def test_bounds_are_indian_midnight(self):
        start, end = bc.period_bounds_utc(date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(start, datetime(2026, 8, 31, 18, 30, tzinfo=timezone.utc))
        self.assertEqual(end,   datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc))

    def test_suggest_next(self):
        self.assertEqual(bc.suggest_next_period(None), (None, None))
        self.assertEqual(bc.suggest_next_period(date(2026, 9, 14)), (date(2026, 9, 15), date(2026, 10, 14)))
        self.assertEqual(bc.suggest_next_period(date(2027, 1, 30)), (date(2027, 1, 31), date(2027, 2, 27)))

    def test_validate(self):
        today = date(2026, 10, 14)
        self.assertIsNone(bc.validate_period(date(2026, 9, 1), date(2026, 10, 11), None, today))
        self.assertIn("generated from", bc.validate_period(date(2026, 9, 1), date(2026, 10, 12), None, today))
        self.assertIn("must start on", bc.validate_period(date(2026, 9, 3), date(2026, 9, 30), date(2026, 8, 31), today))
        self.assertIn("must start on", bc.validate_period(date(2026, 8, 31), date(2026, 9, 30), date(2026, 8, 31), today))
        self.assertIsNone(bc.validate_period(date(2026, 9, 1), date(2026, 9, 30), date(2026, 8, 31), today))
        self.assertIn("on or after", bc.validate_period(date(2026, 9, 5), date(2026, 9, 1), None, today))

    def test_billing_month(self):
        self.assertEqual(bc.billing_month_for(date(2026, 10, 14)), date(2026, 10, 1))


class AmountInWordsTest(unittest.TestCase):
    def test_words(self):
        self.assertEqual(bc.amount_in_words(D("1297.00")), "Rupees One Thousand Two Hundred Ninety Seven Only")
        self.assertEqual(bc.amount_in_words(D("64.85")), "Rupees Sixty Four and Eighty Five Paise Only")
        self.assertEqual(bc.amount_in_words(D("0")), "Rupees Zero Only")
        self.assertEqual(bc.amount_in_words(D("1234567.5")),
                         "Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Fifty Paise Only")
        self.assertEqual(bc.amount_in_words(D("250000000")), "Rupees Twenty Five Crore Only")
        self.assertEqual(bc.amount_in_words(D("1500000000")), "Rupees One Hundred Fifty Crore Only")


if __name__ == "__main__":
    unittest.main()

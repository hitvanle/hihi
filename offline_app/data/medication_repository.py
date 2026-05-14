from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from offline_app.data.db_paths import resolve_db_path
from offline_app.data.medication_first40_catalog import FIRST40_DRUG_CATALOG, SECOND40_DRUG_CATALOG, THIRD40_DRUG_CATALOG, FINAL38_DRUG_CATALOG

DB_PATH = resolve_db_path("hospital_medication.db")


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _pair_key(left: str, right: str) -> str:
    names = sorted([_text(left).lower(), _text(right).lower()])
    return f"{names[0]}|{names[1]}"


@dataclass(slots=True)
class DrugRecord:
    id: int | None = None
    generic_name: str = ""
    brand_name: str = ""
    active_ingredients: str = ""
    category_path: str = ""
    strength_forms: str = ""
    usual_dose: str = ""
    contraindications: str = ""
    cautions: str = ""
    pregnancy: str = ""
    lactation: str = ""
    monitoring: str = ""
    administration_guidance: str = ""


@dataclass(slots=True)
class DoseRule:
    id: int | None = None
    drug_name: str = ""
    renal_min: float | None = None
    renal_max: float | None = None
    child_pugh: str = ""
    age_min: float | None = None
    age_max: float | None = None
    weight_min: float | None = None
    weight_max: float | None = None
    recommendation: str = ""
    warning: str = ""


@dataclass(slots=True)
class InteractionRecord:
    id: int | None = None
    drug_a: str = ""
    drug_b: str = ""
    severity: str = ""
    effect_text: str = ""
    management: str = ""


class MedicationRepository:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._ensure_schema()
        self._seed_if_empty()
        self._sync_drug_catalog()
        from offline_app.data.medication_enrichment import apply_medication_enrichment

        apply_medication_enrichment(self)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drug_dictionary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generic_name TEXT NOT NULL,
                    brand_name TEXT DEFAULT '',
                    active_ingredients TEXT DEFAULT '',
                    category_path TEXT DEFAULT '',
                    strength_forms TEXT DEFAULT '',
                    usual_dose TEXT DEFAULT '',
                    contraindications TEXT DEFAULT '',
                    cautions TEXT DEFAULT '',
                    pregnancy TEXT DEFAULT '',
                    lactation TEXT DEFAULT '',
                    monitoring TEXT DEFAULT ''
                    ,
                    administration_guidance TEXT DEFAULT ''
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(drug_dictionary)").fetchall()}
            if "active_ingredients" not in columns:
                conn.execute("ALTER TABLE drug_dictionary ADD COLUMN active_ingredients TEXT DEFAULT ''")
            if "category_path" not in columns:
                conn.execute("ALTER TABLE drug_dictionary ADD COLUMN category_path TEXT DEFAULT ''")
            if "administration_guidance" not in columns:
                conn.execute("ALTER TABLE drug_dictionary ADD COLUMN administration_guidance TEXT DEFAULT ''")
            conn.execute(
                """
                UPDATE drug_dictionary
                SET active_ingredients = generic_name
                WHERE trim(ifnull(active_ingredients, '')) = ''
                """
            )
            conn.execute(
                """
                UPDATE drug_dictionary
                SET category_path = CASE
                    WHEN lower(generic_name) IN ('warfarin', 'enoxaparin') THEN 'Thuốc tim mạch/Chống đông'
                    WHEN lower(generic_name) = 'digoxin' THEN 'Thuốc tim mạch/Suy tim'
                    WHEN lower(generic_name) = 'amiodarone' THEN 'Thuốc tim mạch/Chống loạn nhịp'
                    WHEN lower(generic_name) = 'spironolactone' THEN 'Thuốc tim mạch/Thuốc huyết áp'
                    WHEN lower(generic_name) = 'metformin' THEN 'Nội tiết/Đái tháo đường'
                    ELSE 'Khác'
                END
                WHERE trim(ifnull(category_path, '')) = ''
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dose_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drug_name TEXT NOT NULL,
                    renal_min REAL,
                    renal_max REAL,
                    child_pugh TEXT DEFAULT '',
                    age_min REAL,
                    age_max REAL,
                    weight_min REAL,
                    weight_max REAL,
                    recommendation TEXT NOT NULL,
                    warning TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drug_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drug_a TEXT NOT NULL,
                    drug_b TEXT NOT NULL,
                    pair_key TEXT NOT NULL UNIQUE,
                    severity TEXT NOT NULL,
                    effect_text TEXT DEFAULT '',
                    management TEXT DEFAULT ''
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_drug_dictionary_generic ON drug_dictionary(generic_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dose_rules_drug ON dose_rules(drug_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_drug_interactions_pair ON drug_interactions(pair_key)")

    def _seed_if_empty(self) -> None:
        with self._connect() as conn:
            existing = conn.execute("SELECT COUNT(*) AS total FROM drug_dictionary").fetchone()
            if existing and int(existing["total"]) > 0:
                return

            drugs = [
                (
                    "Metformin",
                    "Glucophage",
                    "Metformin",
                    "Nội tiết/Đái tháo đường",
                    "500 mg, 850 mg, 1000 mg",
                    "500 mg x 1-2 lan/ngay, tang dan theo duong huyet.",
                    "Toan chuyen hoa, suy than nang.",
                    "Tam ngung khi can quang iod hoac nhiem trung nang.",
                    "Can nhac nguy co-loi ich.",
                    "Thuong dung duoc.",
                    "eGFR, duong huyet, lactate neu nghi toan.",
                ),
                (
                    "Warfarin",
                    "Coumadin",
                    "Warfarin",
                    "Thuốc tim mạch/Chống đông",
                    "1 mg, 2 mg, 5 mg",
                    "Khoi dau 2-5 mg/ngay, dieu chinh theo INR.",
                    "Chay mau dang tien trien, co thai.",
                    "Nhieu tuong tac thuoc va thuc an.",
                    "Chong chi dinh trong thai ky.",
                    "Than trong.",
                    "INR, dau hieu chay mau.",
                ),
                (
                    "Enoxaparin",
                    "Clexane",
                    "Enoxaparin",
                    "Thuốc tim mạch/Chống đông",
                    "20 mg, 40 mg, 60 mg, 80 mg",
                    "Du phong: 40 mg/ngay; dieu tri: 1 mg/kg moi 12h.",
                    "Xuat huyet dang tien trien, giam tieu cau do heparin.",
                    "Can giam lieu khi suy than.",
                    "Than trong.",
                    "Than trong.",
                    "Creatinine, tieu cau, dau hieu xuat huyet.",
                ),
                (
                    "Digoxin",
                    "Lanoxin",
                    "Digoxin",
                    "Thuốc tim mạch/Suy tim",
                    "0.125 mg, 0.25 mg",
                    "0.125-0.25 mg/ngay, giam lieu o nguoi cao tuoi.",
                    "Block AV do cao chua dat may tao nhip.",
                    "Nguy co ngo doc tang o suy than/hypokalemia.",
                    "Can nhac.",
                    "Than trong.",
                    "Nong do digoxin, kali, chuc nang than.",
                ),
                (
                    "Amiodarone",
                    "Cordarone",
                    "Amiodarone",
                    "Thuốc tim mạch/Chống loạn nhịp",
                    "200 mg vien",
                    "Tai lieu tang theo phac do, duy tri thuong 100-200 mg/ngay.",
                    "Nhip cham nang, block AV do cao.",
                    "Tuong tac nhieu, doc gan/tuyen giap/phoi.",
                    "Can nhac nguy co-loi ich.",
                    "Than trong.",
                    "ECG, men gan, TSH, XQ phoi khi can.",
                ),
                (
                    "Spironolactone",
                    "Aldactone",
                    "Spironolactone",
                    "Thuốc tim mạch/Thuốc huyết áp",
                    "25 mg, 50 mg, 100 mg",
                    "25-100 mg/ngay theo chi dinh.",
                    "Tang kali mau, suy than nang.",
                    "Nguy co tang kali khi dung cung ACEi/ARB.",
                    "Than trong.",
                    "Than trong.",
                    "Kali mau, creatinine.",
                ),
            ]
            conn.executemany(
                """
                INSERT INTO drug_dictionary (
                    generic_name, brand_name, active_ingredients, category_path, strength_forms, usual_dose,
                    contraindications, cautions, pregnancy, lactation, monitoring
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                drugs,
            )

            rules = [
                ("Metformin", None, 30, "", None, None, None, None, "Khong khuyen cao dung khi eGFR < 30.", "Nguy co toan chuyen hoa."),
                ("Metformin", 30, 45, "", None, None, None, None, "Toi da 1000 mg/ngay. Theo doi chuc nang than moi 3 thang.", ""),
                ("Metformin", 45, None, "", None, None, None, None, "Co the dung lieu thong thuong neu dung nap tot.", ""),
                ("Enoxaparin", None, 30, "", None, None, None, None, "Can giam tan suat/lieu (vi du 1 mg/kg moi 24h tuy muc tieu).", "Theo doi sat xuat huyet."),
                ("Enoxaparin", 30, None, "", None, None, None, None, "Co the dung phac do thong thuong.", ""),
                ("Digoxin", None, 30, "", None, None, None, None, "Bat dau lieu thap (0.125 mg cach ngay hoac hang ngay tuy benh canh).", "Can theo doi nong do va ECG."),
                ("Digoxin", 30, None, "", 65, None, None, None, "Nguoi >= 65 tuoi: uu tien lieu thap 0.125 mg/ngay.", ""),
                ("Spironolactone", None, None, "", None, None, None, None, "Truoc khi dung: danh gia kali va creatinine.", ""),
                ("Spironolactone", None, 30, "", None, None, None, None, "Can nhac tranh dung hoac lieu rat than trong.", "Nguy co tang kali."),
                ("Warfarin", None, None, "", 75, None, None, None, "Nguoi cao tuoi: khoi dau lieu thap hon va tang cham theo INR.", ""),
                ("Warfarin", None, None, "B", None, None, None, None, "Benh gan Child-Pugh B: can than trong, theo doi INR sat.", ""),
                ("Warfarin", None, None, "C", None, None, None, None, "Child-Pugh C: nguy co chay mau cao, can danh gia chuyen khoa.", ""),
            ]
            conn.executemany(
                """
                INSERT INTO dose_rules (
                    drug_name, renal_min, renal_max, child_pugh, age_min, age_max, weight_min, weight_max, recommendation, warning
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rules,
            )

            interactions = [
                ("Warfarin", "Amiodarone", "Nang", "Tang INR va tang nguy co xuat huyet.", "Can giam lieu warfarin va theo doi INR sat (2-3 lan/tuan luc dau)."),
                ("Warfarin", "Enoxaparin", "Nang", "Tang nguy co chay mau khi phoi hop chong dong.", "Chi phoi hop khi co chi dinh ro rang, theo doi sat xuat huyet/INR."),
                ("Digoxin", "Amiodarone", "Trung binh", "Amiodarone lam tang nong do digoxin.", "Can nhac giam 30-50% lieu digoxin va theo doi nong do."),
                ("Spironolactone", "Enalapril", "Trung binh", "Tang nguy co tang kali mau.", "Theo doi kali va creatinine sau 3-7 ngay, dieu chinh lieu."),
                ("Metformin", "Iohexol", "Nang", "Tang nguy co toan chuyen hoa quanh thoi diem can quang iod.", "Tam ngung metformin truoc/sau can quang theo huong dan va danh gia lai eGFR."),
            ]
            conn.executemany(
                """
                INSERT INTO drug_interactions (drug_a, drug_b, pair_key, severity, effect_text, management)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(a, b, _pair_key(a, b), s, e, m) for a, b, s, e, m in interactions],
            )

    def _sync_drug_catalog(self) -> None:
        catalog = [
            ("Amlodipine", "Norvasc", "Amlodipine", "Thuốc tim mạch/Thuốc huyết áp", "5 mg, 10 mg", "5-10 mg/ngày", "Hạ huyết áp nặng", "Phù cổ chân, hạ huyết áp tư thế", "Thận trọng", "Thường dùng được", "Huyết áp, phù ngoại biên", "Đường dùng: uống, 1 lần/ngày, cùng hoặc không cùng bữa ăn."),
            ("Losartan", "Cozaar", "Losartan", "Thuốc tim mạch/Thuốc huyết áp", "25 mg, 50 mg, 100 mg", "50-100 mg/ngày", "Có thai", "Tăng kali máu, suy thận", "Chống chỉ định trong thai kỳ", "Thận trọng", "Huyết áp, kali, creatinine", "Đường dùng: uống, 1 lần/ngày."),
            ("Perindopril", "Coversyl", "Perindopril", "Thuốc tim mạch/Thuốc huyết áp", "2 mg, 4 mg, 8 mg", "4-8 mg/ngày", "Tiền sử phù mạch với ACEi", "Ho khan, tăng kali, suy thận", "Không khuyến cáo", "Thận trọng", "Huyết áp, kali, creatinine", "Đường dùng: uống, ưu tiên trước ăn sáng."),
            ("Bisoprolol", "Concor", "Bisoprolol", "Thuốc tim mạch/Suy tim", "2.5 mg, 5 mg, 10 mg", "1.25-10 mg/ngày, tăng dần", "Nhịp chậm nặng, block AV độ cao", "Nhịp chậm, hạ huyết áp", "Thận trọng", "Thận trọng", "Mạch, huyết áp, triệu chứng suy tim", "Đường dùng: uống, 1 lần/ngày."),
            ("Carvedilol", "Dilatrend", "Carvedilol", "Thuốc tim mạch/Suy tim", "6.25 mg, 12.5 mg, 25 mg", "3.125-25 mg x 2 lần/ngày", "Suy gan nặng", "Hạ huyết áp, nhịp chậm", "Thận trọng", "Thận trọng", "Mạch, huyết áp, cân nặng", "Đường dùng: uống, dùng cùng bữa ăn để giảm tụt huyết áp."),
            ("Furosemide", "Lasix", "Furosemide", "Thuốc tim mạch/Lợi tiểu", "20 mg, 40 mg", "20-80 mg/ngày tùy đáp ứng", "Vô niệu", "Hạ kali, mất nước", "Thận trọng", "Thận trọng", "Điện giải, creatinine, nước tiểu", "Đường dùng: uống hoặc tiêm tĩnh mạch chậm. IV: thường không quá 4 mg/phút; có thể pha NaCl 0.9%."),
            ("Atorvastatin", "Lipitor", "Atorvastatin", "Thuốc tim mạch/Rối loạn mỡ máu", "10 mg, 20 mg, 40 mg", "10-40 mg/ngày", "Bệnh gan tiến triển", "Tăng men gan, đau cơ", "Không khuyến cáo", "Thận trọng", "AST/ALT, CK khi đau cơ", "Đường dùng: uống, 1 lần/ngày."),
            ("Rosuvastatin", "Crestor", "Rosuvastatin", "Thuốc tim mạch/Rối loạn mỡ máu", "5 mg, 10 mg, 20 mg", "5-20 mg/ngày", "Bệnh gan tiến triển", "Đau cơ, tăng men gan", "Không khuyến cáo", "Thận trọng", "AST/ALT, CK khi cần", "Đường dùng: uống, 1 lần/ngày."),
            ("Aspirin", "Aspirin Protect", "Acetylsalicylic acid", "Thuốc tim mạch/Kháng tiểu cầu", "81 mg, 100 mg", "81-100 mg/ngày", "Xuất huyết đang tiến triển", "Xuất huyết tiêu hóa", "Thận trọng", "Thận trọng", "Dấu hiệu xuất huyết", "Đường dùng: uống sau ăn, nuốt nguyên viên bao tan ruột nếu có."),
            ("Clopidogrel", "Plavix", "Clopidogrel", "Thuốc tim mạch/Kháng tiểu cầu", "75 mg", "75 mg/ngày", "Xuất huyết đang tiến triển", "Nguy cơ chảy máu", "Thận trọng", "Thận trọng", "Dấu hiệu xuất huyết", "Đường dùng: uống, 1 lần/ngày."),
            ("Nitroglycerin", "Nitromint", "Nitroglycerin", "Thuốc tim mạch/Thuốc đau thắt ngực", "0.4 mg xịt/ngậm", "0.4 mg mỗi 5 phút khi đau ngực, tối đa 3 lần", "Hạ huyết áp nặng, dùng cùng sildenafil", "Đau đầu, hạ huyết áp", "Thận trọng", "Thận trọng", "Huyết áp, triệu chứng đau ngực", "Đường dùng: xịt/ngậm dưới lưỡi. Không nuốt ngay, ngồi/ nằm khi dùng."),
            ("Isosorbide mononitrate", "Imdur", "Isosorbide mononitrate", "Thuốc tim mạch/Thuốc đau thắt ngực", "30 mg, 60 mg", "30-60 mg/ngày", "Hạ huyết áp nặng", "Đau đầu, choáng váng", "Thận trọng", "Thận trọng", "Huyết áp, triệu chứng", "Đường dùng: uống, 1 lần/ngày (viên phóng thích chậm không bẻ/nhai)."),
            ("Omeprazole", "Losec", "Omeprazole", "Tiêu hóa/PPI", "20 mg, 40 mg", "20-40 mg/ngày", "Quá mẫn", "Dùng dài hạn có thể giảm Mg/B12", "Thận trọng", "Thận trọng", "Triệu chứng, Mg khi dùng lâu", "Đường dùng: uống trước ăn 30 phút."),
            ("Pantoprazole", "Pantoloc", "Pantoprazole", "Tiêu hóa/PPI", "20 mg, 40 mg", "20-40 mg/ngày", "Quá mẫn", "Dùng dài hạn cần theo dõi", "Thận trọng", "Thận trọng", "Triệu chứng tiêu hóa", "Đường dùng: uống trước ăn; dạng tiêm truyền theo y lệnh."),
            ("Ceftriaxone", "Rocephin", "Ceftriaxone", "Kháng sinh/Cephalosporin", "1 g, 2 g", "1-2 g/ngày", "Quá mẫn cephalosporin", "Tiêu chảy, dị ứng", "Thận trọng", "Thận trọng", "Triệu chứng nhiễm trùng, dị ứng", "Đường dùng: tiêm bắp sâu hoặc tiêm/truyền tĩnh mạch. Pha với nước cất pha tiêm; truyền IV trong 30 phút với 50-100 mL NaCl 0.9%/Glucose 5%. Gợi ý giọt/phút (dây 20 giọt/mL): ~33 giọt/phút cho 50 mL/30 phút, ~67 giọt/phút cho 100 mL/30 phút."),
            ("Levofloxacin", "Tavanic", "Levofloxacin", "Kháng sinh/Quinolone", "500 mg, 750 mg", "500-750 mg/ngày", "Tiền sử bệnh gân do quinolone", "Kéo dài QT, rối loạn đường huyết", "Thận trọng", "Thận trọng", "QT, đường huyết, chức năng thận", "Đường dùng: uống hoặc truyền tĩnh mạch. IV: truyền chậm (thường >= 60 phút với 500 mg)."),
            ("Amoxicillin/Clavulanate", "Augmentin", "Amoxicillin + Clavulanic acid", "Kháng sinh/Penicillin", "500/125 mg, 875/125 mg", "500/125 mg mỗi 8 giờ hoặc 875/125 mg mỗi 12 giờ", "Quá mẫn penicillin", "Tiêu chảy, phát ban", "Thận trọng", "Thận trọng", "Triệu chứng nhiễm trùng, tác dụng phụ tiêu hóa", "Đường dùng: uống, nên dùng đầu bữa ăn."),
            ("Cefotaxime", "Claforan", "Cefotaxime", "Kháng sinh/Cephalosporin", "1 g", "1-2 g mỗi 8-12 giờ", "Quá mẫn cephalosporin", "Tiêu chảy, dị ứng", "Thận trọng", "Thận trọng", "Triệu chứng nhiễm trùng, dấu hiệu dị ứng", "Đường dùng: tiêm tĩnh mạch hoặc tiêm bắp sâu. Có thể pha NaCl 0.9% để truyền IV 20-30 phút."),
            ("Ceftazidime", "Fortum", "Ceftazidime", "Kháng sinh/Cephalosporin", "1 g, 2 g", "1-2 g mỗi 8-12 giờ", "Quá mẫn cephalosporin", "Cần điều chỉnh liều khi suy thận", "Thận trọng", "Thận trọng", "Chức năng thận, triệu chứng nhiễm trùng", "Đường dùng: tiêm/truyền tĩnh mạch hoặc tiêm bắp. Truyền IV 30 phút; ví dụ 100 mL/30 phút ~67 giọt/phút (dây 20 giọt/mL)."),
            ("Cefepime", "Maxipime", "Cefepime", "Kháng sinh/Cephalosporin", "1 g, 2 g", "1-2 g mỗi 8-12 giờ", "Quá mẫn cephalosporin", "Độc thần kinh khi suy thận", "Thận trọng", "Thận trọng", "Ý thức, chức năng thận", "Đường dùng: tiêm/truyền tĩnh mạch hoặc tiêm bắp. Truyền IV thường 30 phút."),
            ("Piperacillin/Tazobactam", "Tazocin", "Piperacillin + Tazobactam", "Kháng sinh/Penicillin", "4.5 g", "4.5 g mỗi 6-8 giờ", "Quá mẫn penicillin", "Tăng natri, giảm kali, cần điều chỉnh theo thận", "Thận trọng", "Thận trọng", "Điện giải, creatinine, đáp ứng nhiễm trùng", "Đường dùng: truyền tĩnh mạch. Pha theo hướng dẫn hãng (thường NaCl 0.9%), truyền 30 phút (hoặc kéo dài theo phác đồ). Gợi ý 100 mL/30 phút ~67 giọt/phút."),
            ("Meropenem", "Meronem", "Meropenem", "Kháng sinh/Carbapenem", "500 mg, 1 g", "1 g mỗi 8 giờ tùy mức độ", "Quá mẫn carbapenem", "Co giật (hiếm)", "Thận trọng", "Thận trọng", "Triệu chứng nhiễm trùng, chức năng thận", "Đường dùng: tiêm/truyền tĩnh mạch. Có thể truyền 15-30 phút; pha bằng NaCl 0.9%. Ví dụ 100 mL/30 phút ~67 giọt/phút."),
            ("Imipenem/Cilastatin", "Tienam", "Imipenem + Cilastatin", "Kháng sinh/Carbapenem", "500 mg", "500 mg mỗi 6-8 giờ", "Quá mẫn carbapenem", "Nguy cơ co giật, cần điều chỉnh theo thận", "Thận trọng", "Thận trọng", "Thần kinh, chức năng thận", "Đường dùng: truyền tĩnh mạch. Truyền chậm 30-60 phút, pha NaCl 0.9%."),
            ("Vancomycin", "Vancocin", "Vancomycin", "Kháng sinh/Glycopeptide", "500 mg, 1 g", "15-20 mg/kg mỗi 8-12 giờ", "Quá mẫn vancomycin", "Độc thận, hội chứng red man", "Thận trọng", "Thận trọng", "Nồng độ đáy, creatinine, nghe", "Đường dùng: truyền tĩnh mạch (không tiêm bolus nhanh). Pha NaCl 0.9%/Glucose 5%. Tốc độ thường không quá 10 mg/phút; 1 g nên truyền >= 100 phút. Công thức giọt/phút: (mL x 20)/phút."),
            ("Linezolid", "Zyvox", "Linezolid", "Kháng sinh/Oxazolidinone", "600 mg", "600 mg mỗi 12 giờ", "Quá mẫn linezolid", "Giảm tiểu cầu, tương tác serotonin", "Thận trọng", "Thận trọng", "Công thức máu, dấu hiệu hội chứng serotonin", "Đường dùng: uống hoặc truyền tĩnh mạch 30-120 phút."),
            ("Azithromycin", "Zithromax", "Azithromycin", "Kháng sinh/Macrolide", "250 mg, 500 mg", "500 mg ngày 1, sau đó 250 mg/ngày hoặc 500 mg/ngày tùy phác đồ", "Quá mẫn macrolide", "Kéo dài QT", "Thận trọng", "Thận trọng", "ECG nếu nguy cơ, triệu chứng tiêu hóa", "Đường dùng: uống; dạng IV truyền theo hướng dẫn (thường >=60 phút)."),
            ("Clarithromycin", "Klacid", "Clarithromycin", "Kháng sinh/Macrolide", "250 mg, 500 mg", "250-500 mg mỗi 12 giờ", "Quá mẫn macrolide", "Tương tác CYP3A4, kéo dài QT", "Thận trọng", "Thận trọng", "Tương tác thuốc, ECG nếu cần", "Đường dùng: uống."),
            ("Doxycycline", "Vibramycin", "Doxycycline", "Kháng sinh/Tetracycline", "100 mg", "100 mg mỗi 12-24 giờ", "Mang thai, trẻ nhỏ", "Kích ứng tiêu hóa, nhạy cảm ánh sáng", "Không khuyến cáo", "Thận trọng", "Triệu chứng tiêu hóa, hướng dẫn tránh nắng", "Đường dùng: uống nhiều nước, tránh nằm ngay sau uống."),
            ("Metronidazole", "Flagyl", "Metronidazole", "Kháng sinh/Nitroimidazole", "250 mg, 500 mg", "500 mg mỗi 8-12 giờ", "Quá mẫn metronidazole", "Buồn nôn, vị kim loại, tránh rượu", "Thận trọng", "Thận trọng", "Triệu chứng tiêu hóa, thần kinh", "Đường dùng: uống hoặc truyền tĩnh mạch; tránh rượu trong khi dùng và 48-72h sau ngừng."),
            ("Clindamycin", "Dalacin C", "Clindamycin", "Kháng sinh/Lincosamide", "300 mg, 600 mg", "300-600 mg mỗi 6-8 giờ", "Quá mẫn clindamycin", "Nguy cơ viêm đại tràng giả mạc", "Thận trọng", "Thận trọng", "Tiêu chảy, đau bụng", "Đường dùng: uống hoặc truyền tĩnh mạch. IV truyền chậm theo nồng độ khuyến cáo."),
            ("Gentamicin", "Garamycin", "Gentamicin", "Kháng sinh/Aminoglycoside", "80 mg", "5-7 mg/kg/ngày (1 lần hoặc chia liều)", "Quá mẫn aminoglycoside", "Độc thận, độc tai", "Thận trọng", "Thận trọng", "Nồng độ đáy, creatinine, nghe", "Đường dùng: tiêm bắp hoặc truyền tĩnh mạch chậm. Có thể pha NaCl 0.9%, truyền 30-60 phút."),
            ("Amikacin", "Amikin", "Amikacin", "Kháng sinh/Aminoglycoside", "500 mg", "15 mg/kg/ngày", "Quá mẫn aminoglycoside", "Độc thận, độc tai", "Thận trọng", "Thận trọng", "Nồng độ đáy, creatinine, nghe", "Đường dùng: tiêm bắp hoặc truyền tĩnh mạch chậm 30-60 phút."),
            ("Colistin", "Coly-Mycin", "Colistimethate sodium", "Kháng sinh/Polymyxin", "1 MIU, 2 MIU", "Theo đơn vị quốc tế và chức năng thận", "Quá mẫn polymyxin", "Độc thận, độc thần kinh", "Thận trọng", "Thận trọng", "Creatinine, triệu chứng thần kinh", "Đường dùng: truyền tĩnh mạch. Pha đúng đơn vị IU theo hướng dẫn, truyền 30-60 phút; theo dõi sát chức năng thận."),
            ("Amoxicillin", "Amoxil", "Amoxicillin", "Kháng sinh/Penicillin", "250 mg, 500 mg", "500 mg mỗi 8 giờ", "Quá mẫn penicillin", "Tiêu chảy, phát ban", "Thận trọng", "Thận trọng", "Triệu chứng nhiễm trùng, dị ứng", "Đường dùng: uống, có thể cùng hoặc không cùng thức ăn."),
            ("Ampicillin/Sulbactam", "Unasyn", "Ampicillin + Sulbactam", "Kháng sinh/Penicillin", "1.5 g, 3 g", "1.5-3 g mỗi 6 giờ", "Quá mẫn penicillin", "Tiêu chảy, phát ban", "Thận trọng", "Thận trọng", "Triệu chứng nhiễm trùng, chức năng gan thận", "Đường dùng: tiêm/truyền tĩnh mạch hoặc tiêm bắp. IV truyền 15-30 phút."),
            ("Cloxacillin", "Orbenin", "Cloxacillin", "Kháng sinh/Penicillin", "500 mg", "500 mg mỗi 6 giờ", "Quá mẫn penicillin", "Rối loạn tiêu hóa", "Thận trọng", "Thận trọng", "Đáp ứng nhiễm trùng", "Đường dùng: uống xa bữa ăn hoặc tiêm tĩnh mạch theo y lệnh."),
            ("Cephalexin", "Keflex", "Cephalexin", "Kháng sinh/Cephalosporin", "250 mg, 500 mg", "500 mg mỗi 6-12 giờ", "Quá mẫn cephalosporin", "Tiêu chảy, phát ban", "Thận trọng", "Thận trọng", "Triệu chứng nhiễm trùng, dị ứng", "Đường dùng: uống."),
            ("Cefuroxime", "Zinnat", "Cefuroxime", "Kháng sinh/Cephalosporin", "250 mg, 500 mg", "250-500 mg mỗi 12 giờ", "Quá mẫn cephalosporin", "Tiêu chảy, buồn nôn", "Thận trọng", "Thận trọng", "Đáp ứng nhiễm trùng", "Đường dùng: uống sau ăn; dạng tiêm dùng IV/IM theo y lệnh."),
            ("Cefixime", "Suprax", "Cefixime", "Kháng sinh/Cephalosporin", "200 mg, 400 mg", "200 mg mỗi 12 giờ hoặc 400 mg/ngày", "Quá mẫn cephalosporin", "Tiêu chảy", "Thận trọng", "Thận trọng", "Triệu chứng nhiễm trùng", "Đường dùng: uống."),
            ("Cefpodoxime", "Vantin", "Cefpodoxime", "Kháng sinh/Cephalosporin", "100 mg, 200 mg", "100-200 mg mỗi 12 giờ", "Quá mẫn cephalosporin", "Rối loạn tiêu hóa", "Thận trọng", "Thận trọng", "Triệu chứng nhiễm trùng", "Đường dùng: uống cùng thức ăn để tăng hấp thu."),
            ("Ertapenem", "Invanz", "Ertapenem", "Kháng sinh/Carbapenem", "1 g", "1 g mỗi 24 giờ", "Quá mẫn carbapenem", "Co giật (hiếm), rối loạn tiêu hóa", "Thận trọng", "Thận trọng", "Đáp ứng nhiễm trùng, chức năng thận", "Đường dùng: truyền tĩnh mạch 30 phút hoặc tiêm bắp sâu (pha lidocaine theo hướng dẫn)."),
            ("Ciprofloxacin", "Cipro", "Ciprofloxacin", "Kháng sinh/Quinolone", "250 mg, 500 mg, 750 mg", "500-750 mg mỗi 12 giờ", "Tiền sử bệnh gân do quinolone", "Kéo dài QT, viêm gân", "Thận trọng", "Thận trọng", "ECG khi nguy cơ, đường huyết, chức năng thận", "Đường dùng: uống; dạng IV truyền chậm tối thiểu 60 phút."),
            ("Moxifloxacin", "Avelox", "Moxifloxacin", "Kháng sinh/Quinolone", "400 mg", "400 mg/ngày", "Kéo dài QT bẩm sinh", "Kéo dài QT, viêm gân", "Thận trọng", "Thận trọng", "ECG, triệu chứng gân", "Đường dùng: uống hoặc truyền tĩnh mạch 60 phút."),
            ("Trimethoprim/Sulfamethoxazole", "Bactrim", "Trimethoprim + Sulfamethoxazole", "Kháng sinh/Sulfonamide", "80/400 mg, 160/800 mg", "160/800 mg mỗi 12 giờ", "Dị ứng sulfonamide", "Ban da nặng, tăng kali", "Không khuyến cáo gần đủ tháng", "Thận trọng", "Công thức máu, kali, creatinine", "Đường dùng: uống; dạng IV truyền theo y lệnh sau pha loãng."),
            ("Fosfomycin", "Monurol", "Fosfomycin trometamol", "Kháng sinh/Khác", "3 g gói", "3 g liều duy nhất hoặc theo phác đồ", "Quá mẫn", "Tiêu chảy, buồn nôn", "Thận trọng", "Thận trọng", "Triệu chứng tiết niệu", "Đường dùng: uống, hòa tan trong nước."),
            ("Tigecycline", "Tygacil", "Tigecycline", "Kháng sinh/Glycylcycline", "50 mg", "Liều nạp 100 mg, sau đó 50 mg mỗi 12 giờ", "Quá mẫn tetracycline", "Buồn nôn, nôn", "Thận trọng", "Thận trọng", "Men gan, đáp ứng lâm sàng", "Đường dùng: truyền tĩnh mạch 30-60 phút sau pha loãng."),
            ("Daptomycin", "Cubicin", "Daptomycin", "Kháng sinh/Lipopeptide", "350 mg, 500 mg", "4-10 mg/kg/ngày theo chỉ định", "Quá mẫn", "Tăng CK, đau cơ", "Thận trọng", "Thận trọng", "CK, chức năng thận", "Đường dùng: tiêm tĩnh mạch chậm hoặc truyền tĩnh mạch theo hướng dẫn sản phẩm."),
            ("Rifampicin", "Rifadin", "Rifampicin", "Kháng sinh/Kháng lao", "150 mg, 300 mg", "8-12 mg/kg/ngày (thường 600 mg/ngày)", "Quá mẫn rifampicin", "Độc gan, tương tác men gan", "Thận trọng", "Thận trọng", "Men gan, tương tác thuốc", "Đường dùng: uống lúc đói, theo phác đồ chuyên khoa."),
            ("Isoniazid", "Nydrazid", "Isoniazid", "Kháng sinh/Kháng lao", "100 mg, 300 mg", "5 mg/kg/ngày (thường 300 mg/ngày)", "Viêm gan cấp", "Độc gan, viêm dây thần kinh ngoại biên", "Thận trọng", "Thận trọng", "Men gan, bổ sung vitamin B6 khi cần", "Đường dùng: uống lúc đói, theo phác đồ chuyên khoa."),
            ("Insulin glargine", "Lantus", "Insulin glargine", "Nội tiết/Đái tháo đường", "100 IU/mL", "Tùy chỉnh theo đường huyết", "Hạ đường huyết nặng", "Hạ đường huyết", "Thận trọng", "Thận trọng", "Đường huyết lúc đói, HbA1c", "Đường dùng: tiêm dưới da (bụng/đùi/cánh tay), không tiêm tĩnh mạch, luân chuyển vị trí tiêm."),
            ("Empagliflozin", "Jardiance", "Empagliflozin", "Nội tiết/Đái tháo đường", "10 mg, 25 mg", "10-25 mg/ngày", "eGFR quá thấp theo hướng dẫn", "Nhiễm nấm tiết niệu, mất nước", "Thận trọng", "Thận trọng", "eGFR, triệu chứng tiết niệu", "Đường dùng: uống, 1 lần/ngày."),
            ("Sitagliptin", "Januvia", "Sitagliptin", "Nội tiết/Đái tháo đường", "25 mg, 50 mg, 100 mg", "25-100 mg/ngày theo chức năng thận", "Quá mẫn", "Cần điều chỉnh theo thận", "Thận trọng", "Thận trọng", "Đường huyết, eGFR", "Đường dùng: uống, 1 lần/ngày."),
            ("Gliclazide", "Diamicron MR", "Gliclazide", "Nội tiết/Đái tháo đường", "30 mg MR, 60 mg MR", "30-120 mg/ngày", "Đái tháo đường type 1", "Hạ đường huyết", "Thận trọng", "Thận trọng", "Đường huyết, triệu chứng hạ đường huyết", "Đường dùng: uống, dùng trong hoặc ngay sau bữa ăn."),
            ("Paracetamol", "Panadol", "Paracetamol", "Giảm đau/Hạ sốt", "500 mg", "500-1000 mg mỗi 6-8 giờ, tối đa 3-4 g/ngày", "Suy gan nặng", "Độc gan khi quá liều", "Thận trọng", "Thận trọng", "Tổng liều/ngày, men gan khi cần", "Đường dùng: uống; khoảng cách liều tối thiểu 4-6 giờ."),
            ("Tramadol", "Ultram", "Tramadol", "Giảm đau", "50 mg", "50-100 mg mỗi 6-8 giờ", "Ngộ độc rượu/các chất ức chế TKTW cấp", "Buồn ngủ, ức chế hô hấp", "Thận trọng", "Thận trọng", "Mức độ đau, tác dụng phụ TKTW", "Đường dùng: uống hoặc tiêm/truyền theo y lệnh; tránh phối hợp rượu và thuốc an thần."),
        ]
        catalog.extend(FIRST40_DRUG_CATALOG)
        catalog.extend(SECOND40_DRUG_CATALOG)
        catalog.extend(THIRD40_DRUG_CATALOG)
        catalog.extend(FINAL38_DRUG_CATALOG)

        with self._connect() as conn:
            for item in catalog:
                (
                    generic_name,
                    brand_name,
                    active_ingredients,
                    category_path,
                    strength_forms,
                    usual_dose,
                    contraindications,
                    cautions,
                    pregnancy,
                    lactation,
                    monitoring,
                    administration_guidance,
                ) = item
                row = conn.execute(
                    "SELECT id FROM drug_dictionary WHERE lower(generic_name) = lower(?) LIMIT 1",
                    (generic_name,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO drug_dictionary (
                            generic_name, brand_name, active_ingredients, category_path, strength_forms, usual_dose,
                            contraindications, cautions, pregnancy, lactation, monitoring, administration_guidance
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        item,
                    )
                    continue

                conn.execute(
                    """
                    UPDATE drug_dictionary
                    SET brand_name = ?,
                        active_ingredients = ?,
                        category_path = ?,
                        strength_forms = ?,
                        usual_dose = ?,
                        contraindications = ?,
                        cautions = ?,
                        pregnancy = ?,
                        lactation = ?,
                        monitoring = ?,
                        administration_guidance = ?
                    WHERE id = ?
                    """,
                    (
                        brand_name,
                        active_ingredients,
                        category_path,
                        strength_forms,
                        usual_dose,
                        contraindications,
                        cautions,
                        pregnancy,
                        lactation,
                        monitoring,
                        administration_guidance,
                        row["id"],
                    ),
                )

    def list_drugs(self, search: str = "") -> list[DrugRecord]:
        keyword = _text(search)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM drug_dictionary
                WHERE ? = ''
                   OR generic_name LIKE ?
                   OR brand_name LIKE ?
                   OR active_ingredients LIKE ?
                   OR contraindications LIKE ?
                ORDER BY category_path COLLATE NOCASE, generic_name COLLATE NOCASE
                """,
                (keyword, f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
            ).fetchall()
        return [self._row_to_drug(row) for row in rows]

    def find_drug(self, name: str) -> DrugRecord | None:
        keyword = _text(name)
        if not keyword:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM drug_dictionary
                WHERE lower(generic_name) = lower(?)
                   OR lower(brand_name) = lower(?)
                LIMIT 1
                """,
                (keyword, keyword),
            ).fetchone()
            if row:
                return self._row_to_drug(row)
            row = conn.execute(
                """
                SELECT *
                FROM drug_dictionary
                WHERE generic_name LIKE ?
                   OR brand_name LIKE ?
                ORDER BY generic_name COLLATE NOCASE
                LIMIT 1
                """,
                (f"%{keyword}%", f"%{keyword}%"),
            ).fetchone()
        return self._row_to_drug(row) if row else None

    def evaluate_dose_rules(
        self,
        drug_name: str,
        *,
        egfr: float | None = None,
        child_pugh: str = "",
        age: float | None = None,
        weight: float | None = None,
    ) -> list[DoseRule]:
        target = _text(drug_name).lower()
        if not target:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM dose_rules
                WHERE lower(drug_name) = ?
                ORDER BY id ASC
                """,
                (target,),
            ).fetchall()

        results: list[DoseRule] = []
        for row in rows:
            rule = self._row_to_rule(row)
            if not self._matches(rule, egfr=egfr, child_pugh=child_pugh, age=age, weight=weight):
                continue
            results.append(rule)
        return results

    def find_interactions(self, drugs: list[str]) -> list[InteractionRecord]:
        normalized = sorted({_text(name).lower() for name in drugs if _text(name)})
        if len(normalized) < 2:
            return []
        pair_keys = []
        for idx, left in enumerate(normalized):
            for right in normalized[idx + 1 :]:
                pair_keys.append(_pair_key(left, right))
        if not pair_keys:
            return []

        placeholders = ", ".join(["?"] * len(pair_keys))
        query = f"""
            SELECT *
            FROM drug_interactions
            WHERE pair_key IN ({placeholders})
            ORDER BY
                CASE severity
                    WHEN 'Nang' THEN 1
                    WHEN 'Trung binh' THEN 2
                    WHEN 'Nhe' THEN 3
                    ELSE 4
                END,
                drug_a COLLATE NOCASE,
                drug_b COLLATE NOCASE
        """
        with self._connect() as conn:
            rows = conn.execute(query, pair_keys).fetchall()
        return [self._row_to_interaction(row) for row in rows]

    def _matches(
        self,
        rule: DoseRule,
        *,
        egfr: float | None,
        child_pugh: str,
        age: float | None,
        weight: float | None,
    ) -> bool:
        if not self._is_in_range(egfr, rule.renal_min, rule.renal_max):
            return False
        if not self._is_in_range(age, rule.age_min, rule.age_max):
            return False
        if not self._is_in_range(weight, rule.weight_min, rule.weight_max):
            return False
        cp = _text(child_pugh).upper()
        if rule.child_pugh and cp and cp != _text(rule.child_pugh).upper():
            return False
        if rule.child_pugh and not cp:
            return False
        return True

    def _is_in_range(self, value: float | None, low: float | None, high: float | None) -> bool:
        if low is None and high is None:
            return True
        if value is None:
            return False
        if low is not None and value < low:
            return False
        if high is not None and value >= high:
            return False
        return True

    def _row_to_drug(self, row: sqlite3.Row) -> DrugRecord:
        return DrugRecord(
            id=row["id"],
            generic_name=_text(row["generic_name"]),
            brand_name=_text(row["brand_name"]),
            active_ingredients=_text(row["active_ingredients"]),
            category_path=_text(row["category_path"]),
            strength_forms=_text(row["strength_forms"]),
            usual_dose=_text(row["usual_dose"]),
            contraindications=_text(row["contraindications"]),
            cautions=_text(row["cautions"]),
            pregnancy=_text(row["pregnancy"]),
            lactation=_text(row["lactation"]),
            monitoring=_text(row["monitoring"]),
            administration_guidance=_text(row["administration_guidance"]),
        )

    def _row_to_rule(self, row: sqlite3.Row) -> DoseRule:
        return DoseRule(
            id=row["id"],
            drug_name=_text(row["drug_name"]),
            renal_min=_float_or_none(row["renal_min"]),
            renal_max=_float_or_none(row["renal_max"]),
            child_pugh=_text(row["child_pugh"]),
            age_min=_float_or_none(row["age_min"]),
            age_max=_float_or_none(row["age_max"]),
            weight_min=_float_or_none(row["weight_min"]),
            weight_max=_float_or_none(row["weight_max"]),
            recommendation=_text(row["recommendation"]),
            warning=_text(row["warning"]),
        )

    def _row_to_interaction(self, row: sqlite3.Row) -> InteractionRecord:
        return InteractionRecord(
            id=row["id"],
            drug_a=_text(row["drug_a"]),
            drug_b=_text(row["drug_b"]),
            severity=_text(row["severity"]),
            effect_text=_text(row["effect_text"]),
            management=_text(row["management"]),
        )

#!/usr/bin/env python3
"""
Faktúra Renamer GUI s Omega integráciou

Načíta export z účtovného SW Omega a automaticky páruje PDF faktúry
podľa externého čísla a sumy.

Výstupný formát: {typ_dokladu}{interné_číslo}-{externé_číslo}-{pôvodný_názov}.pdf
Príklad: DF302025001-259003485-scan.pdf

INŠTALÁCIA:
    pip install pdfplumber pymupdf Pillow pytesseract

PRE OCR (naskenované PDF):
    Windows: Stiahnuť Tesseract z https://github.com/UB-Mannheim/tesseract/wiki
    Linux:   sudo apt install tesseract-ocr tesseract-ocr-slk tesseract-ocr-ces
"""

import os
import re
import csv
import sys
from pathlib import Path
from tkinter import (
    Tk, Frame, Label, Button, Listbox, Entry, Scrollbar, Canvas, Text,
    filedialog, messagebox, StringVar, END, BOTH, LEFT, RIGHT, TOP,
    BOTTOM, X, Y, VERTICAL, HORIZONTAL, SINGLE, N, S, E, W, NW, WORD
)
from tkinter.ttk import Progressbar, Style, Combobox, Treeview

# === KONTROLA ZÁVISLOSTÍ ===
missing_deps = []

try:
    import pdfplumber
except ImportError:
    missing_deps.append("pdfplumber")

try:
    import fitz  # PyMuPDF
except ImportError:
    missing_deps.append("pymupdf")

try:
    from PIL import Image, ImageTk, ImageDraw
except ImportError:
    missing_deps.append("Pillow")

# OCR je voliteľné
OCR_AVAILABLE = False
try:
    import pytesseract

    # Windows: nastav cestu k Tesseract OCR
    import platform
    if platform.system() == "Windows":
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

    pytesseract.get_tesseract_version()
    OCR_AVAILABLE = True
except ImportError:
    pass
except Exception:
    pass

if missing_deps:
    print("=" * 60)
    print("CHÝBAJÚCE ZÁVISLOSTI")
    print("=" * 60)
    print(f"\nNainštalujte ich príkazom:\n")
    print(f"    pip install {' '.join(missing_deps)}")
    print("\n" + "=" * 60)
    sys.exit(1)


def normalize_number(num: str) -> str:
    """Normalizuje číslo pre porovnanie - odstráni medzery, nahradí _ za /."""
    if not num:
        return ""
    num = num.strip()
    num = re.sub(r'\s+', '', num)  # Odstránenie medzier
    num = num.replace('_', '/')     # Nahradenie _ za /
    return num


def extract_digits(num: str) -> str:
    """Extrahuje len číslice z reťazca."""
    if not num:
        return ""
    return re.sub(r'[^\d]', '', num)


def numbers_match(num1: str, num2: str) -> bool:
    """Porovná dve čísla s normalizáciou."""
    n1 = normalize_number(num1)
    n2 = normalize_number(num2)
    if not n1 or not n2:
        return False
    # Presná zhoda alebo jedno obsahuje druhé
    if n1 == n2 or n1 in n2 or n2 in n1:
        return True
    # Porovnanie len číslic (pre prípad 25VF051 vs 25051)
    d1 = extract_digits(n1)
    d2 = extract_digits(n2)
    if len(d1) >= 4 and len(d2) >= 4 and (d1 == d2 or d1 in d2 or d2 in d1):
        return True
    return False


class OmegaRecord:
    """Záznam z Omega exportu."""
    def __init__(self, typ_dokladu: str, interne_cislo: str, externe_cislo: str, suma: float, partner: str, kv_dph: str = ""):
        self.typ_dokladu = typ_dokladu
        self.interne_cislo = interne_cislo
        self.externe_cislo = externe_cislo
        self.externe_normalized = normalize_number(externe_cislo)
        self.kv_dph = kv_dph
        self.kv_dph_normalized = normalize_number(kv_dph)
        # Extrahuj len číslice z KV DPH pre porovnanie (napr. "25VF051" -> "25051")
        self.kv_dph_digits = re.sub(r'[^0-9]', '', kv_dph) if kv_dph else ""
        # Extrahuj len číslice z externého čísla
        self.externe_digits = re.sub(r'[^0-9]', '', externe_cislo) if externe_cislo else ""
        self.suma = suma
        self.partner = partner
        self.matched = False
        self.already_renamed = False  # Už existuje súbor s týmto číslom

    def __str__(self):
        return f"{self.typ_dokladu}{self.interne_cislo} | {self.externe_cislo} | {self.suma:.2f} EUR | {self.partner}"


class PDFData:
    """Dáta extrahované z PDF."""
    def __init__(self, path: Path):
        self.path = path
        self.externe_cislo: str = ""
        self.suma: float = 0.0
        self.all_numbers: list[str] = []
        self.all_sums: list[float] = []
        self.text: str = ""
        self.matched_record: OmegaRecord = None
        self.possible_matches: list = []  # Viacero možných zhôd
        self.needs_manual: bool = False   # Potrebuje manuálne spárovanie


class PDFViewer(Canvas):
    """Widget na zobrazenie PDF."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.image = None
        self.photo = None
        self.pdf_doc = None
        self.current_page = 0
        self.zoom = 1.0

        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", self._on_mousewheel)
        self.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.yview_scroll(1, "units")

    def load_pdf(self, path: str):
        try:
            if self.pdf_doc:
                self.pdf_doc.close()
            self.pdf_doc = fitz.open(path)
            self.current_page = 0
            self.render_page()
            return True
        except Exception as e:
            print(f"Chyba pri načítaní PDF: {e}")
            return False

    def render_page(self):
        if not self.pdf_doc or self.current_page >= len(self.pdf_doc):
            return

        page = self.pdf_doc[self.current_page]
        mat = fitz.Matrix(self.zoom * 1.5, self.zoom * 1.5)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        self.image = img
        self.photo = ImageTk.PhotoImage(img)

        self.delete("all")
        self.create_image(0, 0, anchor=NW, image=self.photo)
        self.config(scrollregion=(0, 0, img.width, img.height))

    def clear(self):
        self.delete("all")
        if self.pdf_doc:
            self.pdf_doc.close()
            self.pdf_doc = None
        self.image = None
        self.photo = None


class FakturaRenamerOmegaGUI:
    """Hlavná GUI aplikácia s Omega integráciou."""

    # Regex patterny pre čísla faktúr
    PATTERNS = [
        (r'(20[2-3]\d[01]\d{5,6})', "Rok+číslo"),
        (r'Faktúra\s+([\d/]+\s*\(\d+\)\s*[\d/]+)', "METRO"),
        (r'([\d/]+\s*\(\d+\)\s*[\d/]+)', "METRO formát"),
        (r'\((\d{3}-\d{6})\)', "V zátvorke"),
        (r'(?:Variabilný symbol|VS)[\s.:/-]*(\d{4,})', "VS"),
        (r'(?:Faktúra|Faktura|Invoice)[\s.:/-]*(?:č\.?)?[\s.:/-]*([A-Z0-9]{2,}[-/]?\d{4,})', "Faktúra"),
        (r'(?:Číslo faktúry|Cislo faktury)[\s.:/-]*(\S+)', "Č. faktúry"),
        (r'(\d{4}[/-]\d{4,})', "RRRR/XXXXX"),
        (r'([A-Z]{2,3}\d{6,})', "Prefix+číslo"),
        (r'(\d{9,10})', "9-10 ciferné"),
    ]

    # Regex pre sumy
    SUMA_PATTERNS = [
        r'(?:Celkom|Spolu|Total|K úhrade|Na úhradu|Suma|Amount)[\s:]*(\d+[.,]\d{2})\s*(?:EUR|€)?',
        r'(\d+[.,]\d{2})\s*(?:EUR|€)',
        r'(?:EUR|€)\s*(\d+[.,]\d{2})',
    ]

    def __init__(self):
        self.root = Tk()
        self.root.title("Faktúra Renamer - Omega integrácia")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 700)

        # Dáta
        self.omega_records: list[OmegaRecord] = []
        self.pdf_files: list[PDFData] = []
        self.current_pdf_index = 0
        self.available_types = {}
        self.selected_types = set()
        self.type_vars = {}
        self.include_zero_sums = False  # Vrátane dokladov s nulovou sumou
        self.omega_sort_by = "externe"  # externe, suma, partner
        self.omega_sort_reverse = False
        self.omega_show_matched = True  # Zobrazovať aj už priradené

        self.folder_path = StringVar()
        self.csv_path = StringVar()
        self.status_text = StringVar(value="1. Načítajte CSV export z Omegy  2. Vyberte priečinok s PDF")
        self.renamed_count = 0
        self.auto_matched = 0

        self._create_widgets()
        self._bind_shortcuts()

    def _create_widgets(self):
        main_frame = Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill=BOTH, expand=True)

        # === Horný panel - CSV a priečinok ===
        top_frame = Frame(main_frame)
        top_frame.pack(fill=X, pady=(0, 10))

        # CSV
        csv_frame = Frame(top_frame)
        csv_frame.pack(fill=X, pady=2)
        Label(csv_frame, text="Omega CSV:").pack(side=LEFT)
        Entry(csv_frame, textvariable=self.csv_path, width=50).pack(side=LEFT, padx=5)
        Button(csv_frame, text="📄 Načítať CSV", command=self._load_csv).pack(side=LEFT)
        self.csv_status = Label(csv_frame, text="", font=("Arial", 9))
        self.csv_status.pack(side=LEFT, padx=10)

        # Priečinok
        folder_frame = Frame(top_frame)
        folder_frame.pack(fill=X, pady=2)
        Label(folder_frame, text="PDF priečinok:").pack(side=LEFT)
        Entry(folder_frame, textvariable=self.folder_path, width=50).pack(side=LEFT, padx=5)
        Button(folder_frame, text="📁 Vybrať", command=self._select_folder).pack(side=LEFT)
        Button(folder_frame, text="🔍 Skenovať a párovať", command=self._scan_and_match).pack(side=LEFT, padx=5)

        # OCR status
        self.ocr_label = Label(top_frame, text="✓ OCR: Aktívne" if OCR_AVAILABLE else "✗ OCR: Nedostupné",
                               fg="green" if OCR_AVAILABLE else "red", font=("Arial", 9))
        self.ocr_label.pack(anchor=E)

        # === Stredný panel ===
        middle_frame = Frame(main_frame)
        middle_frame.pack(fill=BOTH, expand=True)

        middle_frame.columnconfigure(0, weight=1, minsize=300)
        middle_frame.columnconfigure(1, weight=2, minsize=400)
        middle_frame.columnconfigure(2, weight=1, minsize=350)
        middle_frame.rowconfigure(0, weight=1)

        # --- Ľavý panel - PDF súbory ---
        left_frame = Frame(middle_frame, relief="groove", bd=2)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        Label(left_frame, text="📄 PDF súbory:", font=("Arial", 10, "bold")).pack(anchor="w", padx=5, pady=5)

        # Filter
        filter_frame = Frame(left_frame)
        filter_frame.pack(fill=X, padx=5)
        self.filter_var = StringVar(value="all")
        Button(filter_frame, text="Všetky", command=lambda: self._filter_pdfs("all")).pack(side=LEFT)
        Button(filter_frame, text="✓", command=lambda: self._filter_pdfs("matched")).pack(side=LEFT, padx=2)
        Button(filter_frame, text="⚠", command=lambda: self._filter_pdfs("manual")).pack(side=LEFT, padx=2)
        Button(filter_frame, text="✗", command=lambda: self._filter_pdfs("unmatched")).pack(side=LEFT)

        files_scroll = Scrollbar(left_frame)
        files_scroll.pack(side=RIGHT, fill=Y)

        self.files_listbox = Listbox(left_frame, yscrollcommand=files_scroll.set,
                                      selectmode=SINGLE, font=("Arial", 9))
        self.files_listbox.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.files_listbox.bind("<<ListboxSelect>>", self._on_file_select)
        self.files_listbox.bind("<KeyRelease-Up>", self._on_file_key)
        self.files_listbox.bind("<KeyRelease-Down>", self._on_file_key)
        files_scroll.config(command=self.files_listbox.yview)

        # --- Stredný panel - náhľad PDF ---
        center_frame = Frame(middle_frame, relief="groove", bd=2)
        center_frame.grid(row=0, column=1, sticky="nsew", padx=5)

        Label(center_frame, text="👁 Náhľad PDF:", font=("Arial", 10, "bold")).pack(anchor="w", padx=5, pady=5)

        preview_frame = Frame(center_frame)
        preview_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)

        v_scroll = Scrollbar(preview_frame, orient=VERTICAL)
        v_scroll.pack(side=RIGHT, fill=Y)
        h_scroll = Scrollbar(preview_frame, orient=HORIZONTAL)
        h_scroll.pack(side=BOTTOM, fill=X)

        self.pdf_viewer = PDFViewer(preview_frame, bg="gray",
                                     xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        self.pdf_viewer.pack(fill=BOTH, expand=True)
        v_scroll.config(command=self.pdf_viewer.yview)
        h_scroll.config(command=self.pdf_viewer.xview)

        # Ovládanie
        page_frame = Frame(center_frame)
        page_frame.pack(fill=X, padx=5, pady=5)
        Button(page_frame, text="◀", command=self._prev_page, width=3).pack(side=LEFT)
        self.page_label = Label(page_frame, text="Strana: -/-")
        self.page_label.pack(side=LEFT, padx=10)
        Button(page_frame, text="▶", command=self._next_page, width=3).pack(side=LEFT)

        # --- Pravý panel - párovanie ---
        right_frame = Frame(middle_frame, relief="groove", bd=2)
        right_frame.grid(row=0, column=2, sticky="nsew", padx=(5, 0))

        # Extrahované údaje
        Label(right_frame, text="📊 Extrahované z PDF:", font=("Arial", 10, "bold")).pack(anchor="w", padx=5, pady=5)

        extract_frame = Frame(right_frame)
        extract_frame.pack(fill=X, padx=5)

        Label(extract_frame, text="Čísla:").grid(row=0, column=0, sticky="w")
        self.extracted_numbers = Label(extract_frame, text="-", wraplength=300, justify=LEFT)
        self.extracted_numbers.grid(row=0, column=1, sticky="w", padx=5)

        Label(extract_frame, text="Sumy:").grid(row=1, column=0, sticky="w")
        self.extracted_sums = Label(extract_frame, text="-", wraplength=300, justify=LEFT)
        self.extracted_sums.grid(row=1, column=1, sticky="w", padx=5)

        # Nájdená zhoda
        Label(right_frame, text="🔗 Nájdená zhoda v Omege:", font=("Arial", 10, "bold")).pack(anchor="w", padx=5, pady=(15, 5))

        self.match_info = Label(right_frame, text="-", wraplength=320, justify=LEFT,
                                 font=("Arial", 10), fg="green")
        self.match_info.pack(anchor="w", padx=5)

        # Manuálny výber z Omegy
        Label(right_frame, text="📋 Manuálny výber z Omegy:", font=("Arial", 10, "bold")).pack(anchor="w", padx=5, pady=(15, 5))

        # Tlačidlá na triedenie
        sort_frame = Frame(right_frame)
        sort_frame.pack(fill=X, padx=5)
        
        Label(sort_frame, text="Triediť:", font=("Arial", 8)).pack(side=LEFT)
        Button(sort_frame, text="Číslo", command=lambda: self._sort_omega("externe"), 
               font=("Arial", 8), width=6).pack(side=LEFT, padx=2)
        Button(sort_frame, text="Suma", command=lambda: self._sort_omega("suma"),
               font=("Arial", 8), width=6).pack(side=LEFT, padx=2)
        Button(sort_frame, text="Partner", command=lambda: self._sort_omega("partner"),
               font=("Arial", 8), width=6).pack(side=LEFT, padx=2)
        
        # Checkbox pre zobrazenie už priradených
        from tkinter import Checkbutton, BooleanVar
        self.show_matched_var = BooleanVar(value=True)
        Checkbutton(sort_frame, text="Aj priradené", variable=self.show_matched_var,
                    command=self._refresh_omega_listbox, font=("Arial", 8)).pack(side=RIGHT)

        omega_scroll = Scrollbar(right_frame)
        omega_scroll.pack(side=RIGHT, fill=Y)

        self.omega_listbox = Listbox(right_frame, yscrollcommand=omega_scroll.set,
                                      selectmode=SINGLE, font=("Arial", 9), height=8)
        self.omega_listbox.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.omega_listbox.bind("<<ListboxSelect>>", self._on_omega_select)
        omega_scroll.config(command=self.omega_listbox.yview)

        # Nový názov
        Label(right_frame, text="📝 Nový názov:", font=("Arial", 10, "bold")).pack(anchor="w", padx=5, pady=(10, 0))
        self.new_name_label = Label(right_frame, text="-", wraplength=320, justify=LEFT,
                                     font=("Arial", 10), fg="blue")
        self.new_name_label.pack(anchor="w", padx=5, pady=5)

        # Tlačidlá
        actions_frame = Frame(right_frame)
        actions_frame.pack(fill=X, padx=5, pady=10)

        Button(actions_frame, text="✓ PREMENOVAŤ", command=self._rename_file,
               bg="#4CAF50", fg="white", font=("Arial", 11, "bold"), height=2).pack(fill=X, pady=2)

        btn_frame = Frame(actions_frame)
        btn_frame.pack(fill=X, pady=5)
        Button(btn_frame, text="⏭ Preskočiť", command=self._skip_file).pack(side=LEFT, expand=True, fill=X, padx=(0, 2))
        Button(btn_frame, text="🔄 Znova", command=self._rescan_current).pack(side=LEFT, expand=True, fill=X, padx=(2, 0))

        Button(actions_frame, text="✓✓ Premenovať všetky spárované", command=self._rename_all_matched,
               bg="#2196F3", fg="white").pack(fill=X, pady=5)

        # === Spodný panel ===
        bottom_frame = Frame(main_frame)
        bottom_frame.pack(fill=X, pady=(10, 0))

        self.status_label = Label(bottom_frame, textvariable=self.status_text,
                                   anchor="w", relief="sunken", padx=5, font=("Arial", 10))
        self.status_label.pack(fill=X)

        self.progress = Progressbar(bottom_frame, mode="determinate")
        self.progress.pack(fill=X, pady=(5, 0))

    def _bind_shortcuts(self):
        self.root.bind("<Return>", lambda e: self._rename_file())
        self.root.bind("<Escape>", lambda e: self._skip_file())

    def _load_csv(self):
        """Načíta CSV export z Omegy."""
        filepath = filedialog.askopenfilename(
            title="Vyberte CSV export z Omegy",
            filetypes=[("CSV súbory", "*.csv"), ("Všetky súbory", "*.*")]
        )
        if not filepath:
            return

        self.csv_path.set(filepath)
        self.omega_records = []

        try:
            # Skúsime rôzne kódovania
            for encoding in ['cp1250', 'utf-8', 'latin-1']:
                try:
                    with open(filepath, 'r', encoding=encoding) as f:
                        # Oddeľovač je ;
                        reader = csv.reader(f, delimiter=';')
                        header = next(reader)  # Preskočíme hlavičku

                        for row in reader:
                            if len(row) < 52:
                                continue

                            # Správne indexy stĺpcov pre Omega export
                            typ_dokladu = row[23].strip() if len(row) > 23 else ""
                            interne_cislo = row[26].strip() if len(row) > 26 else ""
                            externe_cislo = row[27].strip() if len(row) > 27 else ""
                            suma_str = row[51].strip() if len(row) > 51 else "0"  # Suma spolu [EUR] (evidovaná)
                            partner = row[36].strip() if len(row) > 36 else ""
                            kv_dph = row[94].strip() if len(row) > 94 else ""  # Číslo dokladu KV DPH

                            # Konverzia sumy
                            suma_str = suma_str.replace(',', '.').replace(' ', '')
                            try:
                                suma = float(suma_str) if suma_str else 0.0
                            except ValueError:
                                suma = 0.0

                            if externe_cislo:
                                record = OmegaRecord(typ_dokladu, interne_cislo, externe_cislo, suma, partner, kv_dph)
                                self.omega_records.append(record)

                    break  # Úspešne načítané
                except UnicodeDecodeError:
                    continue

            self.csv_status.config(text=f"✓ Načítaných {len(self.omega_records)} záznamov", fg="green")
            
            # Zistenie dostupných typov dokladov
            self.available_types = {}
            for record in self.omega_records:
                if record.typ_dokladu:
                    if record.typ_dokladu not in self.available_types:
                        self.available_types[record.typ_dokladu] = 0
                    self.available_types[record.typ_dokladu] += 1
            
            # Zobrazenie dialógu pre výber typov
            self._show_type_selection_dialog()

        except Exception as e:
            self.csv_status.config(text=f"✗ Chyba: {e}", fg="red")
            messagebox.showerror("Chyba", f"Nepodarilo sa načítať CSV:\n{e}")

    def _show_type_selection_dialog(self):
        """Zobrazí dialóg pre výber typov dokladov."""
        from tkinter import Toplevel, Checkbutton, IntVar
        
        dialog = Toplevel(self.root)
        dialog.title("Výber typov dokladov")
        dialog.geometry("400x550")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Centrovanie
        dialog.geometry(f"+{self.root.winfo_x() + 200}+{self.root.winfo_y() + 100}")
        
        Label(dialog, text="Vyberte typy dokladov na párovanie:", 
              font=("Arial", 11, "bold")).pack(pady=10)
        
        Label(dialog, text="(Odporúčané: DF, ZDF pre došlé faktúry)", 
              font=("Arial", 9), fg="gray").pack()
        
        # Frame pre checkboxy so scrollom
        frame = Frame(dialog)
        frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        canvas = Canvas(frame)
        scrollbar = Scrollbar(frame, orient=VERTICAL, command=canvas.yview)
        scrollable_frame = Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # Checkboxy pre každý typ
        self.type_vars = {}
        
        # Zoradenie podľa počtu (najčastejšie navrchu)
        sorted_types = sorted(self.available_types.items(), key=lambda x: -x[1])
        
        # Predvolené typy (DF, ZDF)
        default_selected = {'DF', 'ZDF', 'DPF'}
        
        for typ, count in sorted_types:
            var = IntVar(value=1 if typ in default_selected else 0)
            self.type_vars[typ] = var
            
            cb = Checkbutton(scrollable_frame, text=f"{typ} ({count} záznamov)", 
                            variable=var, font=("Arial", 10))
            cb.pack(anchor="w", pady=2)
        
        # Oddeľovač
        separator = Frame(dialog, height=2, bg="gray")
        separator.pack(fill=X, padx=10, pady=10)
        
        # Checkbox pre nulové sumy
        self.include_zero_var = IntVar(value=0)
        zero_cb = Checkbutton(dialog, text="Vrátane dokladov s nulovou sumou (dobropisy, storna...)", 
                              variable=self.include_zero_var, font=("Arial", 9))
        zero_cb.pack(anchor="w", padx=15)
        
        # Tlačidlá
        btn_frame = Frame(dialog)
        btn_frame.pack(fill=X, padx=10, pady=10)
        
        Button(btn_frame, text="Vybrať všetky", 
               command=lambda: self._select_all_types(True)).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Zrušiť všetky", 
               command=lambda: self._select_all_types(False)).pack(side=LEFT, padx=5)
        
        Button(btn_frame, text="✓ Potvrdiť", command=lambda: self._confirm_type_selection(dialog),
               bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side=RIGHT, padx=5)
        
        dialog.wait_window()
    
    def _select_all_types(self, select: bool):
        """Vyberie/zruší všetky typy."""
        for var in self.type_vars.values():
            var.set(1 if select else 0)
    
    def _confirm_type_selection(self, dialog):
        """Potvrdí výber typov a filtruje záznamy."""
        selected_types = {typ for typ, var in self.type_vars.items() if var.get() == 1}
        
        if not selected_types:
            messagebox.showwarning("Upozornenie", "Vyberte aspoň jeden typ dokladu!")
            return
        
        # Uloženie nastavenia pre nulové sumy
        self.include_zero_sums = self.include_zero_var.get() == 1
        
        # Filtrovanie záznamov
        original_count = len(self.omega_records)
        if self.include_zero_sums:
            self.omega_records = [r for r in self.omega_records if r.typ_dokladu in selected_types]
        else:
            self.omega_records = [r for r in self.omega_records if r.typ_dokladu in selected_types and r.suma > 0]
        
        self.selected_types = selected_types
        
        zero_info = " +nulové" if self.include_zero_sums else ""
        self.csv_status.config(
            text=f"✓ {len(self.omega_records)} záznamov ({', '.join(sorted(selected_types))}{zero_info})", 
            fg="green"
        )
        
        self._update_omega_listbox()
        dialog.destroy()

    def _update_omega_listbox(self, filter_text: str = ""):
        """Aktualizuje zoznam Omega záznamov."""
        self.omega_listbox.delete(0, END)
        
        show_matched = self.show_matched_var.get() if hasattr(self, 'show_matched_var') else True
        
        # Filtrovanie
        records_to_show = []
        for record in self.omega_records:
            if record.already_renamed:
                continue
            if not show_matched and record.matched:
                continue
            records_to_show.append(record)
        
        # Triedenie
        if self.omega_sort_by == "externe":
            records_to_show.sort(key=lambda r: r.externe_cislo, reverse=self.omega_sort_reverse)
        elif self.omega_sort_by == "suma":
            records_to_show.sort(key=lambda r: r.suma, reverse=self.omega_sort_reverse)
        elif self.omega_sort_by == "partner":
            records_to_show.sort(key=lambda r: r.partner.lower(), reverse=self.omega_sort_reverse)
        
        for record in records_to_show:
            prefix = "● " if record.matched else ""
            display = f"{prefix}{record.externe_cislo} | {record.suma:.2f}€ | {record.partner[:20]}"
            if not filter_text or filter_text.lower() in display.lower():
                self.omega_listbox.insert(END, display)

    def _sort_omega(self, sort_by: str):
        """Zmení triedenie Omega zoznamu."""
        if self.omega_sort_by == sort_by:
            self.omega_sort_reverse = not self.omega_sort_reverse
        else:
            self.omega_sort_by = sort_by
            self.omega_sort_reverse = False
        
        # Refresh podľa aktuálneho PDF
        if self.pdf_files and self.current_pdf_index < len(self.pdf_files):
            pdf_data = self.pdf_files[self.current_pdf_index]
            self._update_omega_listbox_for_pdf(pdf_data)
        else:
            self._update_omega_listbox()

    def _refresh_omega_listbox(self):
        """Obnoví Omega listbox po zmene checkboxu."""
        if self.pdf_files and self.current_pdf_index < len(self.pdf_files):
            pdf_data = self.pdf_files[self.current_pdf_index]
            self._update_omega_listbox_for_pdf(pdf_data)
        else:
            self._update_omega_listbox()

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Vyberte priečinok s PDF faktúrami")
        if folder:
            self.folder_path.set(folder)

    def _scan_and_match(self):
        """Preskenuje PDF a spáruje s Omega záznamami."""
        folder = self.folder_path.get()
        if not folder:
            messagebox.showwarning("Upozornenie", "Najprv vyberte priečinok!")
            return

        if not self.omega_records:
            messagebox.showwarning("Upozornenie", "Najprv načítajte CSV z Omegy!")
            return

        path = Path(folder)
        if not path.exists():
            messagebox.showerror("Chyba", "Priečinok neexistuje!")
            return

        # Reset
        for record in self.omega_records:
            record.matched = False
            record.already_renamed = False
        self.pdf_files = []
        self.auto_matched = 0

        # Nájdenie všetkých PDF (vrátane už premenovaných)
        all_pdfs = list(path.glob("*.pdf")) + list(path.glob("*.PDF"))
        all_pdfs = sorted(set(all_pdfs))

        # Kontrola už premenovaných súborov - označenie v Omega záznamoch
        # Pattern pre naše premenované súbory: DF302025001-259003485-scan.pdf
        # Používame len skutočné typy dokladov z Omegy, nie FV, FA a pod.
        valid_doc_types = '|'.join(re.escape(t) for t in self.selected_types) if self.selected_types else 'DF|ZDF|DPF|OF|PF'
        renamed_pattern = re.compile(rf'^({valid_doc_types})(\d+)-([^-]+)-(.+)\.pdf$', re.IGNORECASE)
        already_renamed_externes = set()

        for pdf_path in all_pdfs:
            match = renamed_pattern.match(pdf_path.name)
            if match:
                externe_in_name = match.group(3)
                already_renamed_externes.add(normalize_number(externe_in_name))

        # Označenie Omega záznamov, ktoré už majú premenovaný súbor
        for record in self.omega_records:
            if record.externe_normalized in already_renamed_externes:
                record.already_renamed = True

        # Filtrovanie - len nepremenované PDF
        pdf_paths = [f for f in all_pdfs if not renamed_pattern.match(f.name)]

        self.progress["maximum"] = len(pdf_paths) if pdf_paths else 1

        for i, pdf_path in enumerate(pdf_paths):
            self.status_text.set(f"Skenujem: {pdf_path.name}...")
            self.progress["value"] = i + 1
            self.root.update()

            pdf_data = self._extract_pdf_data(pdf_path)
            self._try_match(pdf_data)
            self.pdf_files.append(pdf_data)

        self._update_files_listbox()
        self._update_omega_listbox()

        already_done = sum(1 for r in self.omega_records if r.already_renamed)
        self.status_text.set(f"Hotovo! {self.auto_matched}/{len(self.pdf_files)} auto-spárovaných, {already_done} už premenovaných")

        if self.pdf_files:
            self.files_listbox.selection_set(0)
            self._on_file_select(None)

    def _extract_pdf_data(self, pdf_path: Path) -> PDFData:
        """Extrahuje dáta z PDF."""
        pdf_data = PDFData(pdf_path)

        try:
            # Najprv skúsime extrahovať číslo z názvu súboru
            filename = pdf_path.stem  # Bez prípony
            filename_numbers = self._extract_numbers_from_filename(filename)
            
            doc = fitz.open(str(pdf_path))
            all_text = ""

            for page_num, page in enumerate(doc):
                text = page.get_text()

                # OCR ak treba
                if len(text.strip()) < 30 and OCR_AVAILABLE:
                    mat = fitz.Matrix(2.0, 2.0)
                    pix = page.get_pixmap(matrix=mat)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    try:
                        text = pytesseract.image_to_string(img, lang='slk+ces+eng')
                    except:
                        try:
                            text = pytesseract.image_to_string(img)
                        except:
                            pass

                all_text += text + "\n"

            doc.close()
            pdf_data.text = all_text

            # Extrakcia čísel z textu
            found_numbers = set()
            for pattern, label in self.PATTERNS:
                for match in re.finditer(pattern, all_text, re.IGNORECASE):
                    num = match.group(1).strip()
                    num = re.sub(r'\s+', '', num)  # Odstránenie medzier
                    if len(num) >= 4:
                        found_numbers.add(num)

            # Pridanie čísel z názvu súboru (na začiatok - vyššia priorita)
            pdf_data.all_numbers = filename_numbers + [n for n in found_numbers if n not in filename_numbers]

            # Extrakcia súm
            found_sums = set()
            for pattern in self.SUMA_PATTERNS:
                for match in re.finditer(pattern, all_text, re.IGNORECASE):
                    suma_str = match.group(1).replace(',', '.').replace(' ', '')
                    try:
                        suma = float(suma_str)
                        if suma > 0:
                            found_sums.add(suma)
                    except ValueError:
                        pass

            pdf_data.all_sums = sorted(list(found_sums), reverse=True)

        except Exception as e:
            print(f"Chyba pri spracovaní {pdf_path.name}: {e}")

        return pdf_data

    def _extract_numbers_from_filename(self, filename: str) -> list:
        """Extrahuje potenciálne čísla faktúr z názvu súboru."""
        numbers = []
        
        # Číslo s prefixom na začiatku: FV12508546, FA2024001
        prefix_match = re.match(r'^([A-Z]{1,3})(\d{6,})', filename)
        if prefix_match:
            # Pridaj celé číslo s prefixom aj samotné číslo
            numbers.append(prefix_match.group(1) + prefix_match.group(2))
            numbers.append(prefix_match.group(2))
        
        # METRO formát: 0_0(026)0058_003755 alebo podobné
        metro_match = re.search(r'(\d+[_/]\d+\(\d+\)\d+[_/]\d+)', filename)
        if metro_match:
            numbers.append(metro_match.group(1))
        
        # Číslo na začiatku (bez prefixu): 2025010076-scan.pdf
        start_match = re.match(r'^(\d{6,})', filename)
        if start_match and start_match.group(1) not in numbers:
            numbers.append(start_match.group(1))
        
        # Formát s pomlčkou/podčiarkovníkom: 058-013068
        dash_match = re.search(r'(\d{3}[-_]\d{6})', filename)
        if dash_match:
            numbers.append(dash_match.group(1))
        
        # Všeobecné dlhé čísla v názve
        for match in re.finditer(r'(\d{7,})', filename):
            num = match.group(1)
            if num not in numbers:
                numbers.append(num)
        
        return numbers

    def _try_match(self, pdf_data: PDFData):
        """Pokúsi sa spárovať PDF s Omega záznamom."""
        # Normalizácia čísel z PDF
        pdf_numbers_normalized = [normalize_number(n) for n in pdf_data.all_numbers]
        # Extrahuj len číslice z PDF čísel
        pdf_numbers_digits = [re.sub(r'[^0-9]', '', n) for n in pdf_data.all_numbers]

        # Hľadanie všetkých možných zhôd
        possible_matches = []

        for record in self.omega_records:
            if record.matched or record.already_renamed:
                continue

            # Kontrola externého čísla alebo KV DPH s normalizáciou
            externe_match = False
            for num, num_norm, num_digits in zip(pdf_data.all_numbers, pdf_numbers_normalized, pdf_numbers_digits):
                # Porovnaj s externým číslom
                if numbers_match(num_norm, record.externe_normalized):
                    externe_match = True
                    break
                # Porovnaj s KV DPH číslom
                if record.kv_dph_normalized and numbers_match(num_norm, record.kv_dph_normalized):
                    externe_match = True
                    break
                # Porovnaj len číslice (napr. "25VF051" z PDF vs "25051" z Omega)
                if num_digits and len(num_digits) >= 4:
                    if num_digits == record.externe_digits or num_digits == record.kv_dph_digits:
                        externe_match = True
                        break
                    # Alebo jedno obsahuje druhé (pre dlhšie čísla)
                    if len(num_digits) >= 5:
                        if record.externe_digits and len(record.externe_digits) >= 5:
                            if num_digits in record.externe_digits or record.externe_digits in num_digits:
                                externe_match = True
                                break
                        if record.kv_dph_digits and len(record.kv_dph_digits) >= 5:
                            if num_digits in record.kv_dph_digits or record.kv_dph_digits in num_digits:
                                externe_match = True
                                break

            if not externe_match:
                continue

            # Pre nulové sumy - stačí zhoda externého čísla
            if record.suma == 0:
                possible_matches.append((record, 0.0))
                continue

            # Kontrola sumy (tolerancia 0.02)
            suma_match = False
            matched_suma = 0.0
            for suma in pdf_data.all_sums:
                if abs(suma - record.suma) < 0.02:
                    suma_match = True
                    matched_suma = suma
                    break

            if suma_match:
                possible_matches.append((record, matched_suma))

        # Jednoznačná zhoda - len jedna možnosť
        if len(possible_matches) == 1:
            record, suma = possible_matches[0]
            pdf_data.matched_record = record
            pdf_data.externe_cislo = record.externe_cislo
            pdf_data.suma = suma
            record.matched = True
            self.auto_matched += 1
        elif len(possible_matches) > 1:
            # Viacero možných zhôd - označiť na manuálne spárovanie
            pdf_data.possible_matches = possible_matches
            pdf_data.needs_manual = True
        else:
            pdf_data.possible_matches = []
            pdf_data.needs_manual = False

    def _update_files_listbox(self, filter_type: str = "all"):
        """Aktualizuje zoznam PDF súborov."""
        self.files_listbox.delete(0, END)
        for pdf_data in self.pdf_files:
            if filter_type == "matched" and not pdf_data.matched_record:
                continue
            if filter_type == "unmatched" and (pdf_data.matched_record or pdf_data.needs_manual):
                continue
            if filter_type == "manual" and not pdf_data.needs_manual:
                continue

            if pdf_data.matched_record:
                prefix = "✓ "
            elif pdf_data.needs_manual:
                prefix = "⚠ "  # Potrebuje manuálne spárovanie
            else:
                prefix = "✗ "
            self.files_listbox.insert(END, prefix + pdf_data.path.name)

    def _filter_pdfs(self, filter_type: str):
        """Filtruje PDF súbory."""
        self.filter_var.set(filter_type)
        self._update_files_listbox(filter_type)

    def _on_file_select(self, event):
        """Spracuje výber PDF súboru."""
        selection = self.files_listbox.curselection()
        if not selection:
            return

        # Nájdenie správneho indexu
        selected_text = self.files_listbox.get(selection[0])
        filename = selected_text[2:]  # Odstránenie prefixu "✓ " alebo "✗ "

        for i, pdf_data in enumerate(self.pdf_files):
            if pdf_data.path.name == filename:
                self.current_pdf_index = i
                break

        self._load_current_pdf()

    def _on_file_key(self, event):
        """Spracuje šípky v zozname súborov."""
        # Malé oneskorenie aby sa stihol aktualizovať výber
        self.root.after(10, self._on_file_select, None)

    def _load_current_pdf(self):
        """Načíta aktuálny PDF."""
        if not self.pdf_files or self.current_pdf_index >= len(self.pdf_files):
            return

        pdf_data = self.pdf_files[self.current_pdf_index]

        # Náhľad
        self.pdf_viewer.load_pdf(str(pdf_data.path))
        self._update_page_label()

        # Extrahované údaje
        self.extracted_numbers.config(text=", ".join(pdf_data.all_numbers[:5]) or "-")
        self.extracted_sums.config(text=", ".join([f"{s:.2f}€" for s in pdf_data.all_sums[:5]]) or "-")

        # Zhoda
        if pdf_data.matched_record:
            rec = pdf_data.matched_record
            self.match_info.config(
                text=f"✓ {rec.typ_dokladu}{rec.interne_cislo}\n{rec.externe_cislo} | {rec.suma:.2f}€\n{rec.partner}",
                fg="green"
            )
            self._update_new_name(pdf_data)
        elif pdf_data.needs_manual and pdf_data.possible_matches:
            # Viacero možných zhôd
            matches_text = f"⚠ {len(pdf_data.possible_matches)} možných zhôd:\n"
            for rec, suma in pdf_data.possible_matches[:3]:
                matches_text += f"• {rec.externe_cislo} | {rec.suma:.2f}€\n"
            if len(pdf_data.possible_matches) > 3:
                matches_text += f"... a ďalších {len(pdf_data.possible_matches) - 3}"
            self.match_info.config(text=matches_text, fg="orange")
            self.new_name_label.config(text="Vyberte záznam z Omegy →")
        else:
            self.match_info.config(text="✗ Nenájdená zhoda", fg="red")
            self.new_name_label.config(text="-")

        # Aktualizácia Omega listboxu - ukáž možné zhody navrchu
        self._update_omega_listbox_for_pdf(pdf_data)

    def _update_omega_listbox_for_pdf(self, pdf_data: PDFData):
        """Aktualizuje Omega listbox s prioritou možných zhôd."""
        self.omega_listbox.delete(0, END)
        
        show_matched = self.show_matched_var.get() if hasattr(self, 'show_matched_var') else True

        # Najprv možné zhody (ak existujú)
        if pdf_data.possible_matches:
            self.omega_listbox.insert(END, "─── MOŽNÉ ZHODY ───")
            for record, suma in pdf_data.possible_matches:
                if not record.already_renamed:
                    prefix = "● " if record.matched else ""
                    display = f"► {prefix}{record.externe_cislo} | {record.suma:.2f}€ | {record.partner[:20]}"
                    self.omega_listbox.insert(END, display)
            self.omega_listbox.insert(END, "─── OSTATNÉ ───")

        # Filtrovanie ostatných
        records_to_show = []
        for record in self.omega_records:
            if record.already_renamed:
                continue
            if not show_matched and record.matched:
                continue
            # Preskočiť ak už je v možných zhodách
            is_possible = any(r == record for r, s in pdf_data.possible_matches)
            if not is_possible:
                records_to_show.append(record)
        
        # Triedenie
        if self.omega_sort_by == "externe":
            records_to_show.sort(key=lambda r: r.externe_cislo, reverse=self.omega_sort_reverse)
        elif self.omega_sort_by == "suma":
            records_to_show.sort(key=lambda r: r.suma, reverse=self.omega_sort_reverse)
        elif self.omega_sort_by == "partner":
            records_to_show.sort(key=lambda r: r.partner.lower(), reverse=self.omega_sort_reverse)
        
        for record in records_to_show:
            prefix = "● " if record.matched else ""
            display = f"{prefix}{record.externe_cislo} | {record.suma:.2f}€ | {record.partner[:20]}"
            self.omega_listbox.insert(END, display)

    def _on_omega_select(self, event):
        """Manuálny výber Omega záznamu."""
        selection = self.omega_listbox.curselection()
        if not selection or not self.pdf_files:
            return

        selected_text = self.omega_listbox.get(selection[0])

        # Preskočiť oddeľovače
        if selected_text.startswith("───"):
            return

        # Odstránenie prefixov ► a ●
        selected_text = selected_text.lstrip("► ").lstrip("● ")

        externe_cislo = selected_text.split("|")[0].strip()

        # Nájdenie záznamu (aj už priradeného)
        for record in self.omega_records:
            if record.externe_cislo == externe_cislo and not record.already_renamed:
                pdf_data = self.pdf_files[self.current_pdf_index]

                # Odpárovanie predošlého (ak nie je ten istý záznam použitý inde)
                if pdf_data.matched_record and pdf_data.matched_record != record:
                    # Skontroluj či predošlý záznam nie je použitý iným PDF
                    used_elsewhere = any(
                        p.matched_record == pdf_data.matched_record 
                        for p in self.pdf_files if p != pdf_data
                    )
                    if not used_elsewhere:
                        pdf_data.matched_record.matched = False

                # Nové párovanie
                pdf_data.matched_record = record
                pdf_data.needs_manual = False
                record.matched = True

                self.match_info.config(
                    text=f"✓ {record.typ_dokladu}{record.interne_cislo}\n{record.externe_cislo} | {record.suma:.2f}€\n{record.partner}",
                    fg="green"
                )
                self._update_new_name(pdf_data)
                self._update_omega_listbox_for_pdf(pdf_data)
                
                # Aktualizuj zoznam súborov ale zachovaj pozíciu
                current_selection = self.files_listbox.curselection()
                current_yview = self.files_listbox.yview()
                self._update_files_listbox(self.filter_var.get())
                
                # Obnov pozíciu scrollu
                if current_yview:
                    self.files_listbox.yview_moveto(current_yview[0])
                
                # Vyber aktuálny súbor (nie prvý)
                for i in range(self.files_listbox.size()):
                    item_text = self.files_listbox.get(i)
                    if pdf_data.path.name in item_text:
                        self.files_listbox.selection_clear(0, END)
                        self.files_listbox.selection_set(i)
                        self.files_listbox.see(i)
                        break
                
                break

    def _update_new_name(self, pdf_data: PDFData):
        """Aktualizuje náhľad nového názvu."""
        if pdf_data.matched_record:
            rec = pdf_data.matched_record
            new_name = f"{rec.typ_dokladu}{rec.interne_cislo}-{rec.externe_cislo}-{pdf_data.path.name}"
            new_name = self._sanitize_filename(new_name)
            self.new_name_label.config(text=new_name)

    def _sanitize_filename(self, name: str) -> str:
        """Odstráni nepovolené znaky."""
        if '(' in name and ')' in name:
            name = re.sub(r'\s+', '', name)
        for char in '<>:"/\\|?*':
            name = name.replace(char, '_')
        return name

    def _rename_file(self):
        """Premenuje aktuálny súbor."""
        if not self.pdf_files or self.current_pdf_index >= len(self.pdf_files):
            return

        pdf_data = self.pdf_files[self.current_pdf_index]

        if not pdf_data.matched_record:
            messagebox.showwarning("Upozornenie", "Najprv vyberte záznam z Omegy!")
            return

        rec = pdf_data.matched_record
        new_name = f"{rec.typ_dokladu}{rec.interne_cislo}-{rec.externe_cislo}-{pdf_data.path.name}"
        new_name = self._sanitize_filename(new_name)
        new_path = pdf_data.path.parent / new_name

        if new_path.exists():
            messagebox.showerror("Chyba", f"Súbor {new_name} už existuje!")
            return

        try:
            self.pdf_viewer.clear()
            self.root.update()

            import time
            time.sleep(0.1)

            pdf_data.path.rename(new_path)
            self.renamed_count += 1
            self.status_text.set(f"✓ Premenované: {new_name}")

            # Zapamätaj si pozíciu pred odstránením
            old_index = self.current_pdf_index
            
            # Odstránenie zo zoznamu
            self.pdf_files.pop(self.current_pdf_index)

            if self.pdf_files:
                # Zostať na rovnakej pozícii (alebo poslednej ak sme na konci)
                if self.current_pdf_index >= len(self.pdf_files):
                    self.current_pdf_index = len(self.pdf_files) - 1
                
                self._update_files_listbox(self.filter_var.get())
                
                # Vyber súbor na rovnakej pozícii
                if self.files_listbox.size() > 0:
                    select_index = min(old_index, self.files_listbox.size() - 1)
                    self.files_listbox.selection_clear(0, END)
                    self.files_listbox.selection_set(select_index)
                    self.files_listbox.see(select_index)
                    self._on_file_select(None)
            else:
                self._show_completion()

        except OSError as e:
            messagebox.showerror("Chyba", f"Nepodarilo sa premenovať: {e}")
            self._load_current_pdf()

    def _rename_all_matched(self):
        """Premenuje všetky spárované súbory."""
        matched = [pdf for pdf in self.pdf_files if pdf.matched_record]

        if not matched:
            messagebox.showinfo("Info", "Žiadne spárované súbory na premenovanie")
            return

        if not messagebox.askyesno("Potvrdenie", f"Premenovať {len(matched)} spárovaných súborov?"):
            return

        self.pdf_viewer.clear()
        self.root.update()

        import time
        time.sleep(0.1)

        success = 0
        errors = []

        for pdf_data in matched:
            rec = pdf_data.matched_record
            new_name = f"{rec.typ_dokladu}{rec.interne_cislo}-{rec.externe_cislo}-{pdf_data.path.name}"
            new_name = self._sanitize_filename(new_name)
            new_path = pdf_data.path.parent / new_name

            try:
                if not new_path.exists():
                    pdf_data.path.rename(new_path)
                    success += 1
                else:
                    errors.append(f"{pdf_data.path.name}: už existuje")
            except OSError as e:
                errors.append(f"{pdf_data.path.name}: {e}")

        # Refresh
        self.renamed_count += success
        self._scan_and_match()

        msg = f"Úspešne premenovaných: {success}"
        if errors:
            msg += f"\n\nChyby ({len(errors)}):\n" + "\n".join(errors[:5])
        messagebox.showinfo("Výsledok", msg)

    def _skip_file(self):
        if not self.pdf_files:
            return
        self.current_pdf_index = (self.current_pdf_index + 1) % len(self.pdf_files)
        self._update_files_listbox(self.filter_var.get())
        if self.files_listbox.size() > 0:
            self.files_listbox.selection_set(self.current_pdf_index % self.files_listbox.size())
            self._on_file_select(None)

    def _rescan_current(self):
        if self.pdf_files and self.current_pdf_index < len(self.pdf_files):
            pdf_data = self.pdf_files[self.current_pdf_index]
            if pdf_data.matched_record:
                pdf_data.matched_record.matched = False
            new_data = self._extract_pdf_data(pdf_data.path)
            self._try_match(new_data)
            self.pdf_files[self.current_pdf_index] = new_data
            self._load_current_pdf()
            self._update_files_listbox(self.filter_var.get())

    def _prev_page(self):
        if self.pdf_viewer.pdf_doc and self.pdf_viewer.current_page > 0:
            self.pdf_viewer.current_page -= 1
            self.pdf_viewer.render_page()
            self._update_page_label()

    def _next_page(self):
        if self.pdf_viewer.pdf_doc and self.pdf_viewer.current_page < len(self.pdf_viewer.pdf_doc) - 1:
            self.pdf_viewer.current_page += 1
            self.pdf_viewer.render_page()
            self._update_page_label()

    def _update_page_label(self):
        if self.pdf_viewer.pdf_doc:
            total = len(self.pdf_viewer.pdf_doc)
            current = self.pdf_viewer.current_page + 1
            self.page_label.config(text=f"Strana: {current}/{total}")
        else:
            self.page_label.config(text="Strana: -/-")

    def _show_completion(self):
        self.pdf_viewer.clear()
        self.files_listbox.delete(0, END)
        self.new_name_label.config(text="-")
        self.status_text.set(f"✓ Hotovo! Premenovaných: {self.renamed_count}")
        self.progress["value"] = 100
        messagebox.showinfo("Dokončené", f"Všetky súbory spracované!\n\nPremenovaných: {self.renamed_count}")

    def run(self):
        self.root.mainloop()


def main():
    app = FakturaRenamerOmegaGUI()
    app.run()


if __name__ == "__main__":
    main()

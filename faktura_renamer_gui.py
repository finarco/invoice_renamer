#!/usr/bin/env python3
"""
Faktúra Renamer GUI - Skenovanie PDF súborov a premenovanie podľa čísla faktúry.

INŠTALÁCIA:
    pip install pdfplumber pymupdf Pillow pytesseract

PRE OCR (naskenované PDF):
    Windows: Stiahnuť Tesseract z https://github.com/UB-Mannheim/tesseract/wiki
    Linux:   sudo apt install tesseract-ocr tesseract-ocr-slk tesseract-ocr-ces

Spustenie:
    python faktura_renamer_gui.py
"""

import os
import re
import sys
import threading
from pathlib import Path
from tkinter import (
    Tk, Frame, Label, Button, Listbox, Entry, Scrollbar, Canvas, Text,
    filedialog, messagebox, StringVar, END, BOTH, LEFT, RIGHT, TOP, 
    BOTTOM, X, Y, VERTICAL, HORIZONTAL, SINGLE, N, S, E, W, NW, WORD
)
from tkinter.ttk import Progressbar, Style, Combobox

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
    # Ak máš Tesseract nainštalovaný inde, zmeň túto cestu
    import platform
    if platform.system() == "Windows":
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    
    # Test či je Tesseract nainštalovaný
    pytesseract.get_tesseract_version()
    OCR_AVAILABLE = True
except ImportError:
    pass
except Exception:
    pass  # pytesseract je nainštalovaný, ale Tesseract OCR engine nie

if missing_deps:
    print("=" * 60)
    print("CHÝBAJÚCE ZÁVISLOSTI")
    print("=" * 60)
    print(f"\nNainštalujte ich príkazom:\n")
    print(f"    pip install {' '.join(missing_deps)}")
    print("\n" + "=" * 60)
    sys.exit(1)


class InvoiceCandidate:
    """Reprezentuje nájdené číslo faktúry s pozíciou v PDF."""
    def __init__(self, text: str, page: int = 0, bbox: tuple = None, label: str = ""):
        self.text = text
        self.page = page
        self.bbox = bbox  # (x0, y0, x1, y1)
        self.label = label
    
    def __str__(self):
        return self.text


class PDFViewer(Canvas):
    """Widget na zobrazenie PDF s možnosťou zvýraznenia."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.image = None
        self.photo = None
        self.pdf_doc = None
        self.current_page = 0
        self.zoom = 1.0
        self.highlights = []
        
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", self._on_mousewheel)
        self.bind("<Button-5>", self._on_mousewheel)
    
    def _on_mousewheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.yview_scroll(1, "units")
    
    def load_pdf(self, path: str):
        """Načíta PDF súbor."""
        try:
            if self.pdf_doc:
                self.pdf_doc.close()
            self.pdf_doc = fitz.open(path)
            self.current_page = 0
            self.highlights = []
            self.render_page()
            return True
        except Exception as e:
            print(f"Chyba pri načítaní PDF: {e}")
            return False
    
    def render_page(self):
        """Vykreslí aktuálnu stránku."""
        if not self.pdf_doc or self.current_page >= len(self.pdf_doc):
            return
        
        page = self.pdf_doc[self.current_page]
        mat = fitz.Matrix(self.zoom * 1.5, self.zoom * 1.5)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Vykreslenie zvýraznení
        if self.highlights:
            draw = ImageDraw.Draw(img, "RGBA")
            scale = self.zoom * 1.5
            
            for highlight in self.highlights:
                if highlight.page == self.current_page and highlight.bbox:
                    x0, y0, x1, y1 = highlight.bbox
                    rect = (x0 * scale, y0 * scale, x1 * scale, y1 * scale)
                    draw.rectangle(rect, fill=(255, 255, 0, 100), outline=(255, 200, 0), width=2)
        
        self.image = img
        self.photo = ImageTk.PhotoImage(img)
        
        self.delete("all")
        self.create_image(0, 0, anchor=NW, image=self.photo)
        self.config(scrollregion=(0, 0, img.width, img.height))
    
    def set_highlight(self, candidate: InvoiceCandidate):
        """Nastaví zvýraznenie pre kandidáta."""
        self.highlights = [candidate] if candidate else []
        if candidate and candidate.page != self.current_page:
            self.current_page = candidate.page
        self.render_page()
    
    def clear(self):
        """Vyčistí zobrazenie."""
        self.delete("all")
        if self.pdf_doc:
            self.pdf_doc.close()
            self.pdf_doc = None
        self.image = None
        self.photo = None


class FakturaRenamerGUI:
    """Hlavná GUI aplikácia."""
    
    # Regex patterny pre hľadanie čísel faktúr
    PATTERNS = [
        # Číslo faktúry v štýle 2025010076 (rok + poradové číslo)
        (r'(20[2-3]\d[01]\d{5,6})', "Číslo faktúry RRRRXXXXXX"),
        # METRO formáty - s medzerami aj bez
        (r'Faktúra\s+([\d/]+\s*\(\d+\)\s*[\d/]+)', "METRO Faktúra"),
        (r'([\d/]+\s*\(\d+\)\s*[\d/]+)', "METRO formát"),
        (r'\((\d{3}-\d{6})\)', "Číslo v zátvorke"),
        # Variabilný symbol - vysoká priorita
        (r'(?:Variabilný symbol|Variabilny symbol|VS|Var\.\s*symbol)[\s.:/-]*(\d{4,})', "Variabilný symbol"),
        # Štandardné SK/CZ formáty
        (r'(?:Faktúra|Faktura|Invoice)[\s.:/-]*(?:č\.?|číslo|No\.?|Number)?[\s.:/-]*([A-Z0-9]{2,}[-/]?\d{4,})', "Faktúra"),
        (r'(?:Číslo faktúry|Cislo faktury|Č\.\s*faktúry)[\s.:/-]*(\S+)', "Číslo faktúry"),
        (r'(?:Doklad|Doklad č)[\s.:/-]*(\d+[/-]?\d*)', "Doklad"),
        # Všeobecné formáty
        (r'(\d{4}[/-]\d{4,})', "RRRR/XXXXX"),
        (r'([A-Z]{2,3}\d{6,})', "Prefix + číslo"),
        (r'(\d{9,10})', "9-10 ciferné"),
    ]
    
    def __init__(self):
        self.root = Tk()
        self.root.title("Faktúra Renamer")
        self.root.geometry("1300x850")
        self.root.minsize(1000, 700)
        
        # Dáta
        self.pdf_files: list[Path] = []
        self.current_file_index = 0
        self.candidates: list[InvoiceCandidate] = []
        self.folder_path = StringVar()
        self.status_text = StringVar(value="Vyberte priečinok s PDF súbormi")
        self.renamed_count = 0
        self.extracted_text = ""
        
        self._create_widgets()
        self._bind_shortcuts()
        self._show_ocr_status()
    
    def _show_ocr_status(self):
        """Zobrazí stav OCR."""
        if OCR_AVAILABLE:
            self.ocr_label.config(text="✓ OCR: Aktívne", fg="green")
        else:
            self.ocr_label.config(text="✗ OCR: Nedostupné (pre skeny nainštalujte Tesseract)", fg="red")
    
    def _create_widgets(self):
        """Vytvorí GUI komponenty."""
        main_frame = Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill=BOTH, expand=True)
        
        # === Horný panel ===
        top_frame = Frame(main_frame)
        top_frame.pack(fill=X, pady=(0, 10))
        
        Label(top_frame, text="Priečinok:").pack(side=LEFT)
        Entry(top_frame, textvariable=self.folder_path, width=50).pack(side=LEFT, padx=5)
        Button(top_frame, text="📁 Vybrať...", command=self._select_folder).pack(side=LEFT)
        Button(top_frame, text="🔍 Skenovať", command=self._scan_folder).pack(side=LEFT, padx=5)
        
        self.ocr_label = Label(top_frame, text="", font=("Arial", 9))
        self.ocr_label.pack(side=RIGHT)
        
        # === Stredný panel ===
        middle_frame = Frame(main_frame)
        middle_frame.pack(fill=BOTH, expand=True)
        
        middle_frame.columnconfigure(0, weight=1, minsize=180)
        middle_frame.columnconfigure(1, weight=3, minsize=450)
        middle_frame.columnconfigure(2, weight=2, minsize=350)
        middle_frame.rowconfigure(0, weight=1)
        
        # --- Ľavý panel - zoznam súborov ---
        left_frame = Frame(middle_frame, relief="groove", bd=2)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        Label(left_frame, text="📄 PDF súbory:", font=("Arial", 10, "bold")).pack(anchor="w", padx=5, pady=5)
        
        files_scroll = Scrollbar(left_frame)
        files_scroll.pack(side=RIGHT, fill=Y)
        
        self.files_listbox = Listbox(left_frame, yscrollcommand=files_scroll.set, 
                                      selectmode=SINGLE, font=("Arial", 9))
        self.files_listbox.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.files_listbox.bind("<<ListboxSelect>>", self._on_file_select)
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
                                     xscrollcommand=h_scroll.set,
                                     yscrollcommand=v_scroll.set)
        self.pdf_viewer.pack(fill=BOTH, expand=True)
        
        v_scroll.config(command=self.pdf_viewer.yview)
        h_scroll.config(command=self.pdf_viewer.xview)
        
        # Ovládanie stránok
        page_frame = Frame(center_frame)
        page_frame.pack(fill=X, padx=5, pady=5)
        
        Button(page_frame, text="◀", command=self._prev_page, width=3).pack(side=LEFT)
        self.page_label = Label(page_frame, text="Strana: -/-")
        self.page_label.pack(side=LEFT, padx=10)
        Button(page_frame, text="▶", command=self._next_page, width=3).pack(side=LEFT)
        
        Label(page_frame, text="  Zoom:").pack(side=LEFT, padx=(20, 0))
        self.zoom_combo = Combobox(page_frame, values=["50%", "75%", "100%", "125%", "150%"], 
                                    width=6, state="readonly")
        self.zoom_combo.set("100%")
        self.zoom_combo.pack(side=LEFT, padx=5)
        self.zoom_combo.bind("<<ComboboxSelected>>", self._on_zoom_change)
        
        # --- Pravý panel ---
        right_frame = Frame(middle_frame, relief="groove", bd=2)
        right_frame.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        
        # Nájdené čísla
        Label(right_frame, text="🔢 Nájdené čísla faktúr:", font=("Arial", 10, "bold")).pack(anchor="w", padx=5, pady=5)
        
        candidates_frame = Frame(right_frame)
        candidates_frame.pack(fill=X, padx=5)
        
        candidates_scroll = Scrollbar(candidates_frame)
        candidates_scroll.pack(side=RIGHT, fill=Y)
        
        self.candidates_listbox = Listbox(candidates_frame, yscrollcommand=candidates_scroll.set,
                                           selectmode=SINGLE, font=("Arial", 11), height=8,
                                           bg="white", selectbackground="#4CAF50")
        self.candidates_listbox.pack(fill=BOTH, expand=True)
        self.candidates_listbox.bind("<<ListboxSelect>>", self._on_candidate_select)
        candidates_scroll.config(command=self.candidates_listbox.yview)
        
        # Info label
        self.info_label = Label(right_frame, text="", font=("Arial", 9), fg="gray", wraplength=320)
        self.info_label.pack(anchor="w", padx=5, pady=5)
        
        # Manuálne zadanie
        manual_frame = Frame(right_frame)
        manual_frame.pack(fill=X, padx=5, pady=10)
        
        Label(manual_frame, text="✏️ Manuálne zadanie:", font=("Arial", 10, "bold")).pack(anchor="w")
        self.manual_entry = Entry(manual_frame, font=("Arial", 12))
        self.manual_entry.pack(fill=X, pady=5)
        self.manual_entry.bind("<Return>", lambda e: self._rename_file())
        self.manual_entry.bind("<KeyRelease>", self._on_manual_change)
        
        # Náhľad nového názvu
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
        
        # Extrahovaný text (debug)
        Label(right_frame, text="📋 Extrahovaný text:", font=("Arial", 9)).pack(anchor="w", padx=5, pady=(15, 0))
        
        text_frame = Frame(right_frame)
        text_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        text_scroll = Scrollbar(text_frame)
        text_scroll.pack(side=RIGHT, fill=Y)
        
        self.text_preview = Text(text_frame, height=8, font=("Courier", 8), 
                                  yscrollcommand=text_scroll.set, wrap=WORD)
        self.text_preview.pack(fill=BOTH, expand=True)
        text_scroll.config(command=self.text_preview.yview)
        
        # === Spodný panel ===
        bottom_frame = Frame(main_frame)
        bottom_frame.pack(fill=X, pady=(10, 0))
        
        self.status_label = Label(bottom_frame, textvariable=self.status_text, 
                                   anchor="w", relief="sunken", padx=5, font=("Arial", 10))
        self.status_label.pack(fill=X)
        
        self.progress = Progressbar(bottom_frame, mode="determinate")
        self.progress.pack(fill=X, pady=(5, 0))
    
    def _bind_shortcuts(self):
        """Nastaví klávesové skratky."""
        self.root.bind("<Control-o>", lambda e: self._select_folder())
        self.root.bind("<Return>", lambda e: self._rename_file())
        self.root.bind("<Escape>", lambda e: self._skip_file())
    
    def _select_folder(self):
        """Otvorí dialóg na výber priečinka."""
        folder = filedialog.askdirectory(title="Vyberte priečinok s PDF faktúrami")
        if folder:
            self.folder_path.set(folder)
            self._scan_folder()
    
    def _scan_folder(self):
        """Preskenuje priečinok na PDF súbory."""
        folder = self.folder_path.get()
        if not folder:
            messagebox.showwarning("Upozornenie", "Najprv vyberte priečinok!")
            return
        
        path = Path(folder)
        if not path.exists():
            messagebox.showerror("Chyba", "Priečinok neexistuje!")
            return
        
        # Nájdenie PDF súborov (okrem už premenovaných)
        all_pdfs = list(path.glob("*.pdf")) + list(path.glob("*.PDF"))
        self.pdf_files = sorted([f for f in set(all_pdfs) if not re.match(r'^\d+-', f.name)])
        
        self.files_listbox.delete(0, END)
        for pdf_file in self.pdf_files:
            self.files_listbox.insert(END, pdf_file.name)
        
        self.current_file_index = 0
        self.renamed_count = 0
        
        if self.pdf_files:
            self.status_text.set(f"Nájdených {len(self.pdf_files)} PDF súborov")
            self.files_listbox.selection_set(0)
            self._load_current_file()
        else:
            self.status_text.set("Žiadne PDF súbory na spracovanie")
            self.pdf_viewer.clear()
            self.candidates_listbox.delete(0, END)
    
    def _on_file_select(self, event):
        """Spracuje výber súboru zo zoznamu."""
        selection = self.files_listbox.curselection()
        if selection:
            self.current_file_index = selection[0]
            self._load_current_file()
    
    def _load_current_file(self):
        """Načíta aktuálny PDF súbor."""
        if not self.pdf_files or self.current_file_index >= len(self.pdf_files):
            return
        
        pdf_path = self.pdf_files[self.current_file_index]
        self.status_text.set(f"Načítavam: {pdf_path.name}...")
        self.root.update()
        
        # Načítanie PDF
        self.pdf_viewer.load_pdf(str(pdf_path))
        self._update_page_label()
        
        # Extrakcia čísel faktúr
        self._extract_candidates(pdf_path)
        
        # Progress
        self.progress["value"] = ((self.current_file_index + 1) / len(self.pdf_files)) * 100
        self.status_text.set(f"[{self.current_file_index + 1}/{len(self.pdf_files)}] {pdf_path.name}")
    
    def _extract_candidates(self, pdf_path: Path):
        """Extrahuje kandidátov na číslo faktúry."""
        self.candidates = []
        self.candidates_listbox.delete(0, END)
        self.text_preview.delete(1.0, END)
        self.info_label.config(text="")
        self.extracted_text = ""
        
        try:
            doc = fitz.open(str(pdf_path))
            found_texts = set()
            all_text = ""
            used_ocr = False
            
            for page_num, page in enumerate(doc):
                # Extrakcia textu
                text = page.get_text()
                
                # Ak je text prázdny, skúsime OCR
                if len(text.strip()) < 30:
                    if OCR_AVAILABLE:
                        self.status_text.set(f"OCR strana {page_num + 1}...")
                        self.root.update()
                        
                        mat = fitz.Matrix(2.0, 2.0)
                        pix = page.get_pixmap(matrix=mat)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        
                        try:
                            text = pytesseract.image_to_string(img, lang='slk+ces+eng')
                            used_ocr = True
                        except:
                            try:
                                text = pytesseract.image_to_string(img)
                                used_ocr = True
                            except Exception as e:
                                text = ""
                    else:
                        self.info_label.config(text="⚠️ PDF je sken bez textu. Pre automatickú extrakciu nainštalujte Tesseract OCR.", fg="orange")
                
                all_text += f"--- Strana {page_num + 1} ---\n{text}\n"
                
                # Hľadanie patterns
                for pattern, label in self.PATTERNS:
                    for match in re.finditer(pattern, text, re.IGNORECASE):
                        match_text = match.group(1).strip()
                        
                        if match_text in found_texts or len(match_text) < 3:
                            continue
                        found_texts.add(match_text)
                        
                        # Hľadanie pozície
                        bbox = None
                        text_instances = page.search_for(match_text)
                        if text_instances:
                            rect = text_instances[0]
                            bbox = (rect.x0 - 5, rect.y0 - 5, rect.x1 + 5, rect.y1 + 5)
                        
                        candidate = InvoiceCandidate(match_text, page_num, bbox, label)
                        self.candidates.append(candidate)
            
            doc.close()
            
            # Uloženie textu pre debug
            self.extracted_text = all_text
            self.text_preview.insert(1.0, all_text[:3000])
            
            # Info
            if used_ocr:
                self.info_label.config(text="ℹ️ Použité OCR rozpoznávanie", fg="blue")
            elif len(all_text.strip()) < 50:
                self.info_label.config(text="⚠️ PDF neobsahuje text", fg="orange")
            
            # Pridanie do listboxu
            if self.candidates:
                for candidate in self.candidates[:15]:
                    display = f"{candidate.text}  ({candidate.label})"
                    self.candidates_listbox.insert(END, display)
                
                self.candidates_listbox.selection_set(0)
                self._on_candidate_select(None)
                self.info_label.config(text=f"✓ Nájdených {len(self.candidates)} možností", fg="green")
            else:
                self.info_label.config(text="⚠️ Žiadne čísla nenájdené - zadajte manuálne", fg="orange")
                self.new_name_label.config(text="-")
                
        except Exception as e:
            self.status_text.set(f"Chyba: {e}")
            self.info_label.config(text=f"❌ Chyba: {e}", fg="red")
    
    def _on_candidate_select(self, event):
        """Spracuje výber kandidáta."""
        selection = self.candidates_listbox.curselection()
        if selection and selection[0] < len(self.candidates):
            candidate = self.candidates[selection[0]]
            self.pdf_viewer.set_highlight(candidate)
            self._update_page_label()
            self._update_new_name_preview(candidate.text)
            self.manual_entry.delete(0, END)
    
    def _on_manual_change(self, event):
        """Aktualizuje náhľad pri manuálnom zadaní."""
        text = self.manual_entry.get().strip()
        if text:
            self._update_new_name_preview(text)
            # Odznačenie v listboxe
            self.candidates_listbox.selection_clear(0, END)
    
    def _update_new_name_preview(self, invoice_number: str):
        """Aktualizuje náhľad nového názvu."""
        if not self.pdf_files or self.current_file_index >= len(self.pdf_files):
            return
        
        current_name = self.pdf_files[self.current_file_index].name
        safe_number = self._sanitize_filename(invoice_number)
        new_name = f"{safe_number}-{current_name}"
        self.new_name_label.config(text=new_name)
    
    def _sanitize_filename(self, name: str) -> str:
        """Odstráni nepovolené znaky z názvu súboru."""
        # Najprv odstránime medzery z METRO formátu (napr. "0/0 (026) 0058/003755" -> "0/0(026)0058/003755")
        if '(' in name and ')' in name:
            name = re.sub(r'\s+', '', name)  # Odstráni všetky medzery
        
        # Nahradenie nepovolených znakov
        for char in '<>:"/\\|?*':
            name = name.replace(char, '_')
        return name
    
    def _rename_file(self):
        """Premenuje aktuálny súbor."""
        if not self.pdf_files or self.current_file_index >= len(self.pdf_files):
            return
        
        # Získanie čísla
        invoice_number = self.manual_entry.get().strip()
        
        if not invoice_number:
            selection = self.candidates_listbox.curselection()
            if selection and selection[0] < len(self.candidates):
                invoice_number = self.candidates[selection[0]].text
        
        if not invoice_number:
            messagebox.showwarning("Upozornenie", "Vyberte číslo zo zoznamu alebo ho zadajte manuálne!")
            return
        
        # Premenovanie
        pdf_path = self.pdf_files[self.current_file_index]
        safe_number = self._sanitize_filename(invoice_number)
        new_name = f"{safe_number}-{pdf_path.name}"
        new_path = pdf_path.parent / new_name
        
        if new_path.exists():
            messagebox.showerror("Chyba", f"Súbor {new_name} už existuje!")
            return
        
        try:
            # DÔLEŽITÉ: Zavrieť PDF pred premenovaním!
            self.pdf_viewer.clear()
            self.root.update()  # Počkať na uvoľnenie súboru
            
            import time
            time.sleep(0.1)  # Krátka pauza pre istotu
            
            pdf_path.rename(new_path)
            self.renamed_count += 1
            self.status_text.set(f"✓ Premenované: {new_name}")
            
            # Odstránenie zo zoznamu
            self.pdf_files.pop(self.current_file_index)
            self.files_listbox.delete(self.current_file_index)
            
            if self.pdf_files:
                if self.current_file_index >= len(self.pdf_files):
                    self.current_file_index = len(self.pdf_files) - 1
                self.files_listbox.selection_clear(0, END)
                self.files_listbox.selection_set(self.current_file_index)
                self._load_current_file()
            else:
                self._show_completion()
                
        except OSError as e:
            messagebox.showerror("Chyba", f"Nepodarilo sa premenovať: {e}")
            # Znovu načítať súbor ak premenovanie zlyhalo
            self._load_current_file()
    
    def _skip_file(self):
        """Preskočí aktuálny súbor."""
        if not self.pdf_files:
            return
        
        self.current_file_index = (self.current_file_index + 1) % len(self.pdf_files)
        self.files_listbox.selection_clear(0, END)
        self.files_listbox.selection_set(self.current_file_index)
        self._load_current_file()
    
    def _rescan_current(self):
        """Znovu preskenuje aktuálny súbor."""
        self._load_current_file()
    
    def _prev_page(self):
        if self.pdf_viewer.pdf_doc and self.pdf_viewer.current_page > 0:
            self.pdf_viewer.current_page -= 1
            self.pdf_viewer.highlights = []
            self.pdf_viewer.render_page()
            self._update_page_label()
    
    def _next_page(self):
        if self.pdf_viewer.pdf_doc:
            if self.pdf_viewer.current_page < len(self.pdf_viewer.pdf_doc) - 1:
                self.pdf_viewer.current_page += 1
                self.pdf_viewer.highlights = []
                self.pdf_viewer.render_page()
                self._update_page_label()
    
    def _update_page_label(self):
        if self.pdf_viewer.pdf_doc:
            total = len(self.pdf_viewer.pdf_doc)
            current = self.pdf_viewer.current_page + 1
            self.page_label.config(text=f"Strana: {current}/{total}")
        else:
            self.page_label.config(text="Strana: -/-")
    
    def _on_zoom_change(self, event):
        zoom_str = self.zoom_combo.get().replace("%", "")
        self.pdf_viewer.zoom = int(zoom_str) / 100
        self.pdf_viewer.render_page()
    
    def _show_completion(self):
        self.pdf_viewer.clear()
        self.candidates_listbox.delete(0, END)
        self.new_name_label.config(text="-")
        self.text_preview.delete(1.0, END)
        self.status_text.set(f"✓ Hotovo! Premenovaných: {self.renamed_count}")
        self.progress["value"] = 100
        
        messagebox.showinfo("Dokončené", f"Všetky súbory spracované!\n\nPremenovaných: {self.renamed_count}")
    
    def run(self):
        self.root.mainloop()


def main():
    app = FakturaRenamerGUI()
    app.run()


if __name__ == "__main__":
    main()

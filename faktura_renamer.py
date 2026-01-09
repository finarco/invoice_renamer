#!/usr/bin/env python3
"""
Faktúra Renamer - Skenovanie PDF súborov a premenovanie podľa čísla faktúry.

Použitie:
    python faktura_renamer.py [priečinok]
    
Ak nie je zadaný priečinok, použije sa aktuálny priečinok.

Inštalácia závislostí:
    pip install pdfplumber
"""

import os
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("Chýba knižnica pdfplumber. Nainštalujte ju príkazom:")
    print("  pip install pdfplumber")
    sys.exit(1)


def extract_invoice_numbers(text: str) -> list[str]:
    """
    Extrahuje potenciálne čísla faktúr z textu.
    Hľadá rôzne formáty čísel faktúr.
    """
    patterns = [
        # Slovenské/České formáty
        r'(?:Faktúra|Faktura|Invoice|FA|FV|DF|OF)[\s.:/-]*[#]?\s*(\d{4,}[/-]?\d*)',
        r'(?:Číslo faktúry|Cislo faktury|Invoice No|Invoice Number)[\s.:/-]*[#]?\s*(\d{4,}[/-]?\d*)',
        r'(?:Č\.|Č|č\.|č)[\s]*(?:fa|faktúry|faktury)[\s.:/-]*(\d{4,}[/-]?\d*)',
        # Variabilný symbol (často totožný s číslom faktúry)
        r'(?:Variabilný symbol|Variabilny symbol|VS|V\.S\.)[\s.:/-]*(\d{6,})',
        # Všeobecné formáty čísel faktúr
        r'(\d{8,12})',  # 8-12 ciferné čísla
        r'(\d{4}[/-]\d{3,6})',  # Formát RRRR/XXXXX alebo RRRR-XXXXX
        r'([A-Z]{2,3}[/-]?\d{4,})',  # Prefix s písmenami napr. FA2024001
        r'(\d{2,4}[/-]\d{2,4}[/-]\d{2,6})',  # Formát XX/XX/XXXX
    ]
    
    found = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Vyčistenie a normalizácia
            clean = match.strip()
            if clean and clean not in found and len(clean) >= 4:
                found.append(clean)
    
    return found


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrahuje text z PDF súboru."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"  ⚠️  Chyba pri čítaní PDF: {e}")
    return text


def sanitize_filename(name: str) -> str:
    """Odstráni nepovolené znaky z názvu súboru."""
    # Nahradenie nepovolených znakov
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name


def rename_pdf(pdf_path: Path, invoice_number: str) -> Path | None:
    """
    Premenuje PDF súbor pridaním čísla faktúry na začiatok.
    Vráti novú cestu alebo None ak premenovanie zlyhalo.
    """
    safe_number = sanitize_filename(invoice_number)
    new_name = f"{safe_number}-{pdf_path.name}"
    new_path = pdf_path.parent / new_name
    
    # Kontrola či súbor už neexistuje
    if new_path.exists():
        print(f"  ⚠️  Súbor {new_name} už existuje!")
        return None
    
    try:
        pdf_path.rename(new_path)
        return new_path
    except OSError as e:
        print(f"  ⚠️  Chyba pri premenovaní: {e}")
        return None


def process_pdf(pdf_path: Path) -> bool:
    """
    Spracuje jeden PDF súbor - extrahuje čísla a ponúkne premenovanie.
    Vráti True ak bol súbor premenovaný.
    """
    print(f"\n{'='*60}")
    print(f"📄 Súbor: {pdf_path.name}")
    print(f"{'='*60}")
    
    # Extrakcia textu
    print("  Čítam PDF...")
    text = extract_text_from_pdf(str(pdf_path))
    
    if not text.strip():
        print("  ⚠️  Nepodarilo sa extrahovať text (možno naskenovaný PDF)")
        choice = input("  Chcete zadať číslo faktúry manuálne? (a/n): ").strip().lower()
        if choice == 'a':
            manual = input("  Zadajte číslo faktúry: ").strip()
            if manual:
                new_path = rename_pdf(pdf_path, manual)
                if new_path:
                    print(f"  ✅ Premenované na: {new_path.name}")
                    return True
        return False
    
    # Hľadanie čísel faktúr
    candidates = extract_invoice_numbers(text)
    
    if not candidates:
        print("  ⚠️  Nenašli sa žiadne potenciálne čísla faktúr")
        # Zobraz časť textu pre kontext
        preview = text[:500].replace('\n', ' ')[:200]
        print(f"  Náhľad textu: {preview}...")
        
        choice = input("  Chcete zadať číslo faktúry manuálne? (a/n): ").strip().lower()
        if choice == 'a':
            manual = input("  Zadajte číslo faktúry: ").strip()
            if manual:
                new_path = rename_pdf(pdf_path, manual)
                if new_path:
                    print(f"  ✅ Premenované na: {new_path.name}")
                    return True
        return False
    
    # Zobrazenie nájdených kandidátov
    print(f"\n  Nájdené potenciálne čísla faktúr:")
    for i, candidate in enumerate(candidates[:10], 1):  # Max 10 možností
        print(f"    [{i}] {candidate}")
    print(f"    [m] Zadať manuálne")
    print(f"    [s] Preskočiť tento súbor")
    print(f"    [q] Ukončiť program")
    
    # Výber používateľa
    while True:
        choice = input("\n  Vyberte číslo faktúry (1-{}, m, s, q): ".format(min(len(candidates), 10))).strip().lower()
        
        if choice == 'q':
            print("\n👋 Ukončujem program...")
            sys.exit(0)
        
        if choice == 's':
            print("  ⏭️  Preskakujem...")
            return False
        
        if choice == 'm':
            manual = input("  Zadajte číslo faktúry: ").strip()
            if manual:
                new_path = rename_pdf(pdf_path, manual)
                if new_path:
                    print(f"  ✅ Premenované na: {new_path.name}")
                    return True
            continue
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(candidates[:10]):
                selected = candidates[idx]
                new_path = rename_pdf(pdf_path, selected)
                if new_path:
                    print(f"  ✅ Premenované na: {new_path.name}")
                    return True
                continue
        except ValueError:
            pass
        
        print("  ⚠️  Neplatná voľba, skúste znova")


def main():
    # Určenie priečinka
    if len(sys.argv) > 1:
        folder = Path(sys.argv[1])
    else:
        folder = Path.cwd()
    
    if not folder.exists():
        print(f"❌ Priečinok neexistuje: {folder}")
        sys.exit(1)
    
    if not folder.is_dir():
        print(f"❌ Nie je priečinok: {folder}")
        sys.exit(1)
    
    # Nájdenie PDF súborov
    pdf_files = list(folder.glob("*.pdf")) + list(folder.glob("*.PDF"))
    pdf_files = sorted(set(pdf_files))  # Odstránenie duplikátov
    
    if not pdf_files:
        print(f"📁 V priečinku {folder} sa nenašli žiadne PDF súbory")
        sys.exit(0)
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           FAKTÚRA RENAMER - Premenovanie faktúr              ║
╠══════════════════════════════════════════════════════════════╣
║  Priečinok: {str(folder)[:45]:<45} ║
║  Nájdených PDF súborov: {len(pdf_files):<35} ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Spracovanie súborov
    renamed_count = 0
    skipped_count = 0
    
    for pdf_path in pdf_files:
        # Preskočenie už premenovaných (začínajú číslom a pomlčkou)
        if re.match(r'^\d+-', pdf_path.name):
            print(f"\n⏭️  Preskakujem (už premenované): {pdf_path.name}")
            skipped_count += 1
            continue
        
        if process_pdf(pdf_path):
            renamed_count += 1
    
    # Súhrn
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                         SÚHRN                                ║
╠══════════════════════════════════════════════════════════════╣
║  Celkom PDF súborov: {len(pdf_files):<38} ║
║  Premenovaných: {renamed_count:<43} ║
║  Preskočených (už premenované): {skipped_count:<27} ║
╚══════════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()

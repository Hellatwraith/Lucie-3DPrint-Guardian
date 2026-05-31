#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lucie Print Guardian
Mini vérificateur de fichiers Anycubic Photon Workshop .pm4n avant impression résine.

Objectif :
- détecter les fichiers incomplets/corrompus ;
- vérifier la présence de la table LAYERDEF ;
- contrôler le nombre de couches ;
- repérer les couches répétées ou anormalement identiques ;
- générer un rapport simple avant de lancer l'impression.

Création : Hell@Wraith @ AI Guardian Pro @ 2026
"""

from __future__ import annotations

import hashlib
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


APP_NAME = "Lucie Print Guardian"
SUPPORTED_EXTENSIONS = {".pm4n", ".pm5", ".pw0", ".pws", ".photon", ".ctb"}


@dataclass
class LayerInfo:
    index: int
    offset: int
    size: int
    z_or_param_1: float
    exposure_or_param_2: float
    param_3: float
    layer_height: float
    raw_hash: str


@dataclass
class AnalysisResult:
    file_path: Path
    file_size: int
    verdict: str
    score: int
    errors: List[str]
    warnings: List[str]
    infos: List[str]
    layers: List[LayerInfo]


def read_u32(data: bytes, offset: int) -> Optional[int]:
    if offset < 0 or offset + 4 > len(data):
        return None
    return struct.unpack_from("<I", data, offset)[0]


def read_f32(data: bytes, offset: int) -> Optional[float]:
    if offset < 0 or offset + 4 > len(data):
        return None
    return struct.unpack_from("<f", data, offset)[0]


def short_hash(blob: bytes) -> str:
    return hashlib.sha1(blob).hexdigest()[:12]


def find_layerdef(data: bytes) -> int:
    return data.find(b"LAYERDEF")


def parse_layerdef(data: bytes, errors: List[str], warnings: List[str], infos: List[str]) -> List[LayerInfo]:
    """
    Parse heuristique du bloc LAYERDEF des fichiers Anycubic récents.

    Structure observée :
    LAYERDEF + 4 octets NULL + uint32 taille_table + uint32 nombre_couches
    puis nombre_couches entrées de 32 octets.
    Chaque entrée commence généralement par :
    uint32 offset_image_couche
    uint32 taille_image_couche
    puis des floats/paramètres d'exposition.
    """
    idx = find_layerdef(data)
    if idx == -1:
        errors.append("Section critique LAYERDEF absente. Le fichier peut afficher une miniature correcte mais contenir des couches illisibles.")
        return []

    infos.append(f"Section LAYERDEF trouvée à l'octet {idx}.")

    table_size = read_u32(data, idx + 12)
    layer_count = read_u32(data, idx + 16)

    if table_size is None or layer_count is None:
        errors.append("Impossible de lire la taille de table ou le nombre de couches.")
        return []

    infos.append(f"Nombre de couches déclaré : {layer_count}.")
    infos.append(f"Taille de table déclarée : {table_size} octets.")

    if layer_count == 0:
        errors.append("Nombre de couches égal à zéro.")
        return []

    if layer_count > 20000:
        errors.append(f"Nombre de couches irréaliste : {layer_count}.")
        return []

    expected_size = 4 + layer_count * 32
    if abs(int(table_size) - expected_size) > 64:
        warnings.append(
            f"Taille LAYERDEF inhabituelle : {table_size} octets, attendu environ {expected_size} octets."
        )

    entries_start = idx + 20
    entries_end = entries_start + layer_count * 32

    if entries_end > len(data):
        errors.append("La table LAYERDEF dépasse la fin du fichier : fichier probablement tronqué.")
        return []

    layers: List[LayerInfo] = []
    bad_offsets = 0
    zero_sizes = 0
    impossible_sizes = 0

    for i in range(layer_count):
        off = entries_start + i * 32
        img_offset = read_u32(data, off)
        img_size = read_u32(data, off + 4)
        p1 = read_f32(data, off + 8) or 0.0
        p2 = read_f32(data, off + 12) or 0.0
        p3 = read_f32(data, off + 16) or 0.0
        lh = read_f32(data, off + 20) or 0.0

        if img_offset is None or img_size is None:
            bad_offsets += 1
            continue

        if img_size == 0:
            zero_sizes += 1

        if img_offset <= 0 or img_offset >= len(data):
            bad_offsets += 1
            raw = b""
        elif img_offset + img_size > len(data):
            impossible_sizes += 1
            raw = data[img_offset: min(len(data), img_offset + max(0, img_size))]
        else:
            raw = data[img_offset: img_offset + img_size]

        layers.append(
            LayerInfo(
                index=i,
                offset=img_offset,
                size=img_size,
                z_or_param_1=p1,
                exposure_or_param_2=p2,
                param_3=p3,
                layer_height=lh,
                raw_hash=short_hash(raw) if raw else "EMPTY_OR_BAD",
            )
        )

    if bad_offsets:
        errors.append(f"{bad_offsets} couches pointent vers un offset invalide.")
    if impossible_sizes:
        errors.append(f"{impossible_sizes} couches dépassent la fin du fichier.")
    if zero_sizes:
        warnings.append(f"{zero_sizes} couches ont une taille de données égale à zéro.")

    return layers


def check_repetition(layers: List[LayerInfo], errors: List[str], warnings: List[str], infos: List[str]) -> None:
    if not layers:
        return

    sizes = [l.size for l in layers]
    hashes = [l.raw_hash for l in layers]

    first_hash = hashes[0]
    first_repeats = sum(1 for h in hashes if h == first_hash)

    unique_hashes = len(set(hashes))
    unique_sizes = len(set(sizes))

    infos.append(f"Tailles de couche uniques : {unique_sizes}.")
    infos.append(f"Empreintes de couche uniques : {unique_hashes}.")
    infos.append(f"Répétitions de la première couche : {first_repeats}/{len(layers)}.")

    if first_repeats > len(layers) * 0.50:
        errors.append(
            "La première couche semble répétée sur plus de 50% du fichier. Risque majeur de colonne/raft imprimé sur toute la hauteur."
        )
    elif first_repeats > len(layers) * 0.10:
        warnings.append(
            "La première couche est répétée de manière inhabituelle. Vérifier l'aperçu couche par couche."
        )

    if unique_hashes <= max(3, len(layers) * 0.01):
        errors.append("Très peu de couches différentes détectées. Fichier probablement corrompu ou mal slicé.")

    # Détection de longs blocs consécutifs identiques.
    longest_run = 1
    current_run = 1
    run_hash = hashes[0]

    for h in hashes[1:]:
        if h == run_hash:
            current_run += 1
        else:
            longest_run = max(longest_run, current_run)
            run_hash = h
            current_run = 1
    longest_run = max(longest_run, current_run)

    infos.append(f"Plus longue séquence de couches identiques : {longest_run}.")

    if longest_run > 100:
        warnings.append(
            f"Longue séquence de {longest_run} couches identiques. Peut être normal sur un cylindre, mais à vérifier visuellement."
        )
    if longest_run > len(layers) * 0.30:
        errors.append(
            f"Séquence identique très longue ({longest_run} couches). Suspicion forte de couche bloquée/répétée."
        )


def analyse_file(path: Path) -> AnalysisResult:
    errors: List[str] = []
    warnings: List[str] = []
    infos: List[str] = []
    layers: List[LayerInfo] = []

    if not path.exists():
        return AnalysisResult(path, 0, "❌ FICHIER INTROUVABLE", 0, ["Fichier introuvable."], [], [], [])

    file_size = path.stat().st_size
    infos.append(f"Fichier : {path.name}")
    infos.append(f"Taille : {file_size:,} octets ({file_size / 1024 / 1024:.2f} Mo)")

    if file_size < 1024 * 1024:
        warnings.append("Fichier très petit pour une impression résine. Vérifier qu'il ne s'agit pas d'un export incomplet.")

    data = path.read_bytes()

    if data.startswith(b"ANYCUBIC"):
        infos.append("Signature ANYCUBIC détectée.")
    else:
        warnings.append("Signature ANYCUBIC non détectée en début de fichier. L'analyse reste heuristique.")

    if b"HEADER" in data[:512]:
        infos.append("Bloc HEADER détecté.")
    else:
        warnings.append("Bloc HEADER non trouvé au début du fichier.")

    layers = parse_layerdef(data, errors, warnings, infos)
    check_repetition(layers, errors, warnings, infos)

    # Contrôles généraux offsets croissants.
    if layers:
        offsets = [l.offset for l in layers]
        non_monotonic = sum(1 for a, b in zip(offsets, offsets[1:]) if b <= a)
        if non_monotonic:
            warnings.append(f"{non_monotonic} offsets de couches ne sont pas strictement croissants.")
        else:
            infos.append("Offsets de couches croissants : OK.")

        layer_heights = [l.layer_height for l in layers if 0.001 <= l.layer_height <= 1.0]
        if layer_heights:
            avg_lh = sum(layer_heights) / len(layer_heights)
            infos.append(f"Épaisseur moyenne de couche lue : {avg_lh:.4f} mm.")

    score = 100
    score -= len(errors) * 35
    score -= len(warnings) * 10
    score = max(0, min(100, score))

    if errors:
        verdict = "❌ NE PAS IMPRIMER"
    elif warnings:
        verdict = "⚠️ À VÉRIFIER AVANT IMPRESSION"
    else:
        verdict = "✅ FICHIER PROBABLEMENT SAIN"

    return AnalysisResult(path, file_size, verdict, score, errors, warnings, infos, layers)


def build_report(result: AnalysisResult) -> str:
    lines = []
    lines.append("=" * 68)
    lines.append(f"{APP_NAME} - Rapport d'analyse")
    lines.append("Création : Hell@Wraith - AI Guardian Pro @ 2026")
    lines.append("=" * 68)
    lines.append("")
    lines.append(f"Verdict : {result.verdict}")
    lines.append(f"Score confiance : {result.score}/100")
    lines.append("")

    if result.errors:
        lines.append("❌ ERREURS CRITIQUES")
        for e in result.errors:
            lines.append(f" - {e}")
        lines.append("")

    if result.warnings:
        lines.append("⚠️ ALERTES")
        for w in result.warnings:
            lines.append(f" - {w}")
        lines.append("")

    lines.append("ℹ️ INFORMATIONS")
    for i in result.infos:
        lines.append(f" - {i}")

    if result.layers:
        lines.append("")
        lines.append("Échantillon de couches")
        for idx in sorted(set([0, len(result.layers)//4, len(result.layers)//2, int(len(result.layers)*0.75), len(result.layers)-1])):
            l = result.layers[idx]
            lines.append(
                f" - Layer {l.index:04d} | offset={l.offset} | size={l.size} | hash={l.raw_hash} | layer_h={l.layer_height:.4f}"
            )

    lines.append("")
    lines.append("Note Lucie : un fichier validé ici n'empêche pas la vérification visuelle dans le slicer,")
    lines.append("mais il évite déjà les fichiers façon 'menhir hexagonal surprise'.")
    return "\n".join(lines)


class LuciePrintGuardianApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APP_NAME)
        root.geometry("900x650")
        root.minsize(760, 520)

        self.current_report = ""

        top = tk.Frame(root, padx=12, pady=10)
        top.pack(fill=tk.X)

        title = tk.Label(top, text=APP_NAME, font=("Segoe UI", 18, "bold"))
        title.pack(side=tk.LEFT)

        btn = tk.Button(top, text="Choisir un fichier à analyser", command=self.choose_file, height=2)
        btn.pack(side=tk.RIGHT)

        self.drop_label = tk.Label(
            root,
            text="Analyse les fichiers .pm4n / Anycubic avant impression.\n"
                 "Astuce : commence par le fichier exporté final, celui qui partira sur la clé USB.",
            font=("Segoe UI", 11),
            padx=12,
            pady=8,
            justify=tk.LEFT,
        )
        self.drop_label.pack(fill=tk.X)

        self.text = scrolledtext.ScrolledText(root, wrap=tk.WORD, font=("Consolas", 10))
        self.text.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        bottom = tk.Frame(root, padx=12, pady=10)
        bottom.pack(fill=tk.X)

        save_btn = tk.Button(bottom, text="Sauvegarder le rapport .txt", command=self.save_report)
        save_btn.pack(side=tk.RIGHT)

        quit_btn = tk.Button(bottom, text="Fermer", command=root.destroy)
        quit_btn.pack(side=tk.RIGHT, padx=8)

        self.show_intro()

    def show_intro(self) -> None:
        intro = (
            f"{APP_NAME}\n\n"
            "Clique sur « Choisir un fichier à analyser » puis sélectionne ton fichier d'impression.\n\n"
            "Le logiciel vérifie notamment :\n"
            " - présence de la section LAYERDEF ;\n"
            " - nombre de couches ;\n"
            " - offsets et tailles de couches ;\n"
            " - répétition suspecte de la première couche ;\n"
            " - longues séquences de couches identiques.\n\n"
            "Important : ce contrôle ne remplace pas l'aperçu visuel couche par couche dans Photon Workshop,\n"
            "mais il bloque déjà les fichiers manifestement cassés.\n"
        )
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, intro)

    def choose_file(self) -> None:
        filetypes = [
            ("Fichiers résine", "*.pm4n *.pm5 *.pw0 *.pws *.photon *.ctb"),
            ("Tous les fichiers", "*.*"),
        ]
        filename = filedialog.askopenfilename(title="Choisir un fichier d'impression", filetypes=filetypes)
        if filename:
            self.run_analysis(Path(filename))

    def run_analysis(self, path: Path) -> None:
        try:
            result = analyse_file(path)
            self.current_report = build_report(result)
            self.text.delete("1.0", tk.END)
            self.text.insert(tk.END, self.current_report)

            if result.errors:
                messagebox.showerror(APP_NAME, "Analyse terminée : NE PAS IMPRIMER.")
            elif result.warnings:
                messagebox.showwarning(APP_NAME, "Analyse terminée : fichier à vérifier.")
            else:
                messagebox.showinfo(APP_NAME, "Analyse terminée : fichier probablement sain.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Erreur pendant l'analyse :\n{exc}")

    def save_report(self) -> None:
        if not self.current_report.strip():
            messagebox.showwarning(APP_NAME, "Aucun rapport à sauvegarder.")
            return

        filename = filedialog.asksaveasfilename(
            title="Sauvegarder le rapport",
            defaultextension=".txt",
            filetypes=[("Rapport texte", "*.txt"), ("Tous les fichiers", "*.*")],
        )
        if filename:
            Path(filename).write_text(self.current_report, encoding="utf-8")
            messagebox.showinfo(APP_NAME, "Rapport sauvegardé.")


def main() -> None:
    # Mode ligne de commande : python lucie_print_guardian.py fichier.pm4n
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        result = analyse_file(path)
        print(build_report(result))
        sys.exit(1 if result.errors else 0)

    root = tk.Tk()
    LuciePrintGuardianApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

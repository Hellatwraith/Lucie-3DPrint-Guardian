#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lucie Print Guardian
Mini vérificateur de fichiers d'impression résine avant impression.

Description :
    Lucie Print Guardian analyse les fichiers issus de slicers résine,
    notamment Anycubic Photon Workshop, afin de détecter certains signes
    de corruption avant de lancer une impression.

Objectifs :
    - détecter les fichiers incomplets ou corrompus ;
    - vérifier la présence de la table LAYERDEF ;
    - contrôler le nombre de couches déclaré ;
    - repérer les couches répétées ou anormalement identiques ;
    - signaler les offsets invalides ou incohérents ;
    - générer un rapport simple exploitable avant impression.

Formats ciblés :
    .pm4n, .pm5, .pw0, .pws, .photon, .ctb

Note importante :
    Cette analyse est heuristique. Elle ne remplace pas la vérification visuelle
    couche par couche dans le slicer ou sur l'imprimante, mais elle permet déjà
    d'intercepter des fichiers manifestement suspects avant de gaspiller résine,
    FEP, temps et énergie.

Création :
    Hell@Wraight (HellAtWraight) - AI Guardian Pro @ 2025

Copyright :
    AI Guardian Pro @ 2025
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


APP_NAME = "Lucie Print Guardian"
APP_VERSION = "1.1.0-fr"
APP_AUTHOR = "Hell@Wraight (HellAtWraight) - AI Guardian Pro @ 2025"
APP_COPYRIGHT = "Copyright (c) 2025 Hell@Wraight - AI Guardian Pro"
CONTACT = "contact@aiguardianpro.com - À l'attention de Hella"

SUPPORTED_EXTENSIONS = {".pm4n", ".pm5", ".pw0", ".pws", ".photon", ".ctb"}


@dataclass
class LayerInfo:
    """Informations minimales extraites pour une couche d'impression."""

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
    """Résultat complet d'une analyse de fichier."""

    file_path: Path
    file_size: int
    verdict: str
    score: int
    errors: List[str]
    warnings: List[str]
    infos: List[str]
    layers: List[LayerInfo]


def read_u32(data: bytes, offset: int) -> Optional[int]:
    """Lit un entier non signé 32 bits little-endian à l'offset donné."""
    if offset < 0 or offset + 4 > len(data):
        return None
    return struct.unpack_from("<I", data, offset)[0]


def read_f32(data: bytes, offset: int) -> Optional[float]:
    """Lit un float 32 bits little-endian à l'offset donné."""
    if offset < 0 or offset + 4 > len(data):
        return None
    return struct.unpack_from("<f", data, offset)[0]


def short_hash(blob: bytes) -> str:
    """Retourne une empreinte courte d'un bloc de données."""
    return hashlib.sha1(blob).hexdigest()[:12]


def find_layerdef(data: bytes) -> int:
    """Recherche la section LAYERDEF dans le fichier."""
    return data.find(b"LAYERDEF")


def parse_layerdef(
    data: bytes,
    errors: List[str],
    warnings: List[str],
    infos: List[str],
) -> List[LayerInfo]:
    """
    Parse heuristique du bloc LAYERDEF des fichiers Anycubic récents.

    Structure observée sur les fichiers PM4N :
        LAYERDEF
        + 4 octets NULL
        + uint32 taille_table
        + uint32 nombre_couches
        + nombre_couches entrées de 32 octets

    Chaque entrée commence généralement par :
        uint32 offset_image_couche
        uint32 taille_image_couche
        puis des floats / paramètres d'exposition.

    Cette structure peut varier selon les versions de slicer et de firmware.
    L'objectif est donc de détecter les incohérences évidentes, pas de décoder
    officiellement tout le format.
    """
    idx = find_layerdef(data)
    if idx == -1:
        errors.append(
            "Section critique LAYERDEF absente. Le fichier peut afficher une "
            "miniature correcte mais contenir des couches illisibles."
        )
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
            f"Taille LAYERDEF inhabituelle : {table_size} octets, "
            f"attendu environ {expected_size} octets."
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
            raw = data[img_offset:min(len(data), img_offset + max(0, img_size))]
        else:
            raw = data[img_offset:img_offset + img_size]

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


def check_repetition(
    layers: List[LayerInfo],
    errors: List[str],
    warnings: List[str],
    infos: List[str],
) -> None:
    """Recherche les répétitions anormales de couches."""
    if not layers:
        return

    sizes = [layer.size for layer in layers]
    hashes = [layer.raw_hash for layer in layers]

    first_hash = hashes[0]
    first_repeats = sum(1 for h in hashes if h == first_hash)

    unique_hashes = len(set(hashes))
    unique_sizes = len(set(sizes))

    infos.append(f"Tailles de couche uniques : {unique_sizes}.")
    infos.append(f"Empreintes de couche uniques : {unique_hashes}.")
    infos.append(f"Répétitions de la première couche : {first_repeats}/{len(layers)}.")

    if first_repeats > len(layers) * 0.50:
        errors.append(
            "La première couche semble répétée sur plus de 50% du fichier. "
            "Risque majeur de colonne/raft imprimé sur toute la hauteur."
        )
    elif first_repeats > len(layers) * 0.10:
        warnings.append(
            "La première couche est répétée de manière inhabituelle. "
            "Vérifier l'aperçu couche par couche."
        )

    if unique_hashes <= max(3, len(layers) * 0.01):
        errors.append("Très peu de couches différentes détectées. Fichier probablement corrompu ou mal slicé.")

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
            f"Longue séquence de {longest_run} couches identiques. "
            "Peut être normal sur une géométrie répétitive, mais à vérifier visuellement."
        )

    if longest_run > len(layers) * 0.30:
        errors.append(
            f"Séquence identique très longue ({longest_run} couches). "
            "Suspicion forte de couche bloquée/répétée."
        )


def analyse_file(path: Path) -> AnalysisResult:
    """Analyse un fichier d'impression et retourne un rapport structuré."""
    errors: List[str] = []
    warnings: List[str] = []
    infos: List[str] = []
    layers: List[LayerInfo] = []

    if not path.exists():
        return AnalysisResult(path, 0, "❌ FICHIER INTROUVABLE", 0, ["Fichier introuvable."], [], [], [])

    suffix = path.suffix.lower()
    if suffix and suffix not in SUPPORTED_EXTENSIONS:
        warnings.append(
            f"Extension '{suffix}' non listée dans les formats ciblés. "
            "L'analyse reste possible mais peut être moins fiable."
        )

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

    if layers:
        offsets = [layer.offset for layer in layers]
        non_monotonic = sum(1 for a, b in zip(offsets, offsets[1:]) if b <= a)
        if non_monotonic:
            warnings.append(f"{non_monotonic} offsets de couches ne sont pas strictement croissants.")
        else:
            infos.append("Offsets de couches croissants : OK.")

        layer_heights = [layer.layer_height for layer in layers if 0.001 <= layer.layer_height <= 1.0]
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
    """Construit le rapport texte affiché et exportable."""
    lines = []
    lines.append("=" * 68)
    lines.append(f"{APP_NAME} v{APP_VERSION} - Rapport d'analyse")
    lines.append(f"Création : {APP_AUTHOR}")
    lines.append(f"Copyright : {APP_COPYRIGHT}")
    lines.append("=" * 68)
    lines.append("")
    lines.append(f"Verdict : {result.verdict}")
    lines.append(f"Score confiance : {result.score}/100")
    lines.append("")

    if result.errors:
        lines.append("❌ ERREURS CRITIQUES")
        for error in result.errors:
            lines.append(f" - {error}")
        lines.append("")

    if result.warnings:
        lines.append("⚠️ ALERTES")
        for warning in result.warnings:
            lines.append(f" - {warning}")
        lines.append("")

    lines.append("ℹ️ INFORMATIONS")
    for info in result.infos:
        lines.append(f" - {info}")

    if result.layers:
        lines.append("")
        lines.append("Échantillon de couches")
        checkpoints = sorted(
            set(
                [
                    0,
                    len(result.layers) // 4,
                    len(result.layers) // 2,
                    int(len(result.layers) * 0.75),
                    len(result.layers) - 1,
                ]
            )
        )
        for idx in checkpoints:
            layer = result.layers[idx]
            lines.append(
                f" - Layer {layer.index:04d} | offset={layer.offset} | "
                f"size={layer.size} | hash={layer.raw_hash} | "
                f"layer_h={layer.layer_height:.4f}"
            )

    lines.append("")
    lines.append("Note Lucie : un fichier validé ici n'empêche pas la vérification visuelle dans le slicer,")
    lines.append("mais il évite déjà les fichiers façon « menhir hexagonal surprise ». 😄")
    return "\n".join(lines)


class LuciePrintGuardianApp:
    """Interface graphique Tkinter."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(f"{APP_NAME} v{APP_VERSION}")
        root.geometry("900x650")
        root.minsize(760, 520)

        self.current_report = ""
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        top = tk.Frame(root, padx=12, pady=10)
        top.pack(fill=tk.X)

        title = tk.Label(top, text=APP_NAME, font=("Segoe UI", 18, "bold"))
        title.pack(side=tk.LEFT)

        btn = tk.Button(top, text="Choisir un fichier à analyser", command=self.choose_file, height=2)
        btn.pack(side=tk.RIGHT)

        self.drop_label = tk.Label(
            root,
            text=(
                "Analyse les fichiers .pm4n / Anycubic avant impression.\n"
                "Astuce : commence par le fichier exporté final, celui qui partira sur la clé USB."
            ),
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

        quit_btn = tk.Button(bottom, text="Fermer", command=self.on_close)
        quit_btn.pack(side=tk.RIGHT, padx=8)

        self.show_intro()


    def on_close(self) -> None:
        """
        Ferme l'application et libère immédiatement les ressources Windows.

        Pourquoi os._exit(0) ?
        Sous Windows, lorsqu'une application Tkinter est lancée via un .bat,
        un processus Python peut parfois rester accroché quelques secondes
        ou conserver le dossier courant en utilisation. Cette sortie forcée
        évite les consoles fantômes et les dossiers impossibles à renommer.
        """
        try:
            self.current_report = ""
            try:
                self.text.delete("1.0", tk.END)
            except Exception:
                pass
            try:
                self.root.quit()
            except Exception:
                pass
            try:
                self.root.destroy()
            except Exception:
                pass
        finally:
            os._exit(0)

    def show_intro(self) -> None:
        intro = (
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "Clique sur « Choisir un fichier à analyser » puis sélectionne ton fichier d'impression.\n\n"
            "Le logiciel vérifie notamment :\n"
            " - présence de la section LAYERDEF ;\n"
            " - nombre de couches ;\n"
            " - offsets et tailles de couches ;\n"
            " - répétition suspecte de la première couche ;\n"
            " - longues séquences de couches identiques.\n\n"
            "Important : ce contrôle ne remplace pas l'aperçu visuel couche par couche dans Photon Workshop,\n"
            "mais il peut éviter de lancer une impression sur un fichier manifestement corrompu.\n\n"
            f"Création : {APP_AUTHOR}\n"
            f"Copyright : {APP_COPYRIGHT}\n"
            f"Contact : {CONTACT}\n\n"
            "Note Lucie : aucun menhir hexagonal ne devrait franchir cette porte sans contrôle. 😄"
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


def run_cli() -> int:
    """Point d'entrée CLI."""
    parser = argparse.ArgumentParser(
        prog="app",
        description="Vérifie rapidement un fichier d'impression résine avant lancement.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Chemin du fichier à analyser (.pm4n, .pm5, .pw0, .pws, .photon, .ctb).",
    )
    parser.add_argument(
        "--report",
        "-r",
        help="Chemin de sortie pour sauvegarder le rapport texte.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} v{APP_VERSION}",
    )

    args = parser.parse_args()

    if not args.file:
        root = tk.Tk()
        LuciePrintGuardianApp(root)
        root.mainloop()
        return 0

    result = analyse_file(Path(args.file))
    report = build_report(result)
    print(report)

    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")

    return 1 if result.errors else 0


def main() -> None:
    """Lance l'application en mode graphique ou CLI."""
    sys.exit(run_cli())


if __name__ == "__main__":
    main()

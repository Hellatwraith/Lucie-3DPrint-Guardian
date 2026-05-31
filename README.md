# Lucie Print Guardian

## Présentation

**Lucie Print Guardian** est un outil de vérification préventive destiné aux fichiers d'impression résine.

Son objectif est d'analyser un fichier avant son transfert vers une imprimante 3D résine afin d'identifier certaines anomalies connues pouvant conduire à des impressions ratées, à une consommation excessive de résine ou à des pertes de temps importantes.

Le projet a été créé suite à un incident réel au cours duquel un fichier Photon Workshop corrompu a provoqué l'impression répétée d'une couche de support sur toute la hauteur de la pièce, transformant une impression normale en un impressionnant menhir hexagonal de résine.

---

## Objectif

Lucie Print Guardian agit comme une étape de contrôle qualité avant impression.

Le logiciel permet notamment de détecter :

* les fichiers incomplets ou corrompus ;
* l'absence de section `LAYERDEF` ;
* les tables de couches incohérentes ;
* les offsets de couches invalides ;
* les couches répétées ;
* les séquences anormalement longues de couches identiques ;
* certaines corruptions connues observées sur les formats compatibles Anycubic Photon Workshop.

---

## Formats pris en charge

Formats actuellement analysés :

* `.pm4n`
* `.pm5`
* `.pw0`
* `.pws`
* `.photon`
* `.ctb`

> L'analyse est principalement optimisée pour les fichiers générés par les versions récentes d'Anycubic Photon Workshop.
>
> Les autres formats sont analysés selon des méthodes heuristiques et peuvent ne pas bénéficier du même niveau de détection.

---

## Installation

### Prérequis

* Python 3.10 ou supérieur
* Tkinter (généralement inclus avec Python sous Windows)

Aucune dépendance externe n'est requise.

---

## Utilisation graphique

Sous Windows :

1. Télécharger ou cloner le projet.
2. Lancer `LANCER_LUCIE_PRINT_GUARDIAN.bat`.
3. Cliquer sur **Choisir un fichier à analyser**.
4. Sélectionner le fichier d'impression.
5. Consulter le rapport généré.

### Résultats possibles

| Statut                         | Signification                               |
| ------------------------------ | ------------------------------------------- |
| ✅ FICHIER PROBABLEMENT SAIN    | Aucun problème majeur détecté               |
| ⚠️ À VÉRIFIER AVANT IMPRESSION | Anomalies nécessitant une vérification      |
| ❌ NE PAS IMPRIMER              | Corruption ou incohérence critique détectée |

---

## Utilisation en ligne de commande

Analyse simple :

```bash
python lucie_print_guardian.py mon_fichier.pm4n
```

Le mode ligne de commande est principalement destiné aux utilisateurs avancés souhaitant intégrer l'outil dans leurs propres procédures de contrôle.

---

## Limitations

Lucie Print Guardian n'est pas un slicer.

Le logiciel ne remplace pas :

* la vérification visuelle couche par couche ;
* le contrôle de la géométrie du modèle ;
* les tests mécaniques de l'imprimante ;
* le contrôle du plateau, du FEP ou de la résine ;
* les procédures habituelles de validation avant impression.

Même lorsqu'un fichier est déclaré sain, une vérification visuelle reste fortement recommandée.

---

## Non-affiliation

Lucie Print Guardian est un projet indépendant développé par Hell@Wraight dans le cadre des activités d'AI Guardian Pro.

Ce projet n'est ni affilié, ni approuvé, ni sponsorisé par Anycubic ou par toute autre société mentionnée dans la documentation.

Les marques, logiciels, formats ou noms commerciaux cités sont utilisés uniquement à des fins d'identification technique et demeurent la propriété de leurs détenteurs respectifs.

Anycubic et ses représentants ne pourront être tenus responsables des résultats obtenus avec ce logiciel ou de son utilisation.

---

## Contributions

Les signalements de bugs, suggestions d'amélioration et retours d'expérience sont les bienvenus.

Si vous découvrez un nouveau type de corruption ou un comportement inhabituel sur un format supporté, n'hésitez pas à ouvrir une Issue GitHub.

Chaque fichier problématique analysé permet d'améliorer les capacités de détection du projet.

---

## Structure du projet

```text
lucie-print-guardian/
├── lucie_print_guardian.py
├── LANCER_LUCIE_PRINT_GUARDIAN.bat
├── README.md
├── LICENSE
└── .gitignore
```

---

## Auteur

**Hell@Wraight (HellAtWraight)**

Projet développé dans le cadre d'AI Guardian Pro.

Copyright © 2025 Hell@Wraight - AI Guardian Pro

---

## Note Lucie

Lucie Print Guardian a été créé après avoir sacrifié plusieurs centaines de millilitres de résine à un mystérieux phénomène désormais connu sous le nom de :

**« l'Incident du Menhir Hexagonal »**

Depuis, les fichiers suspects sont invités à passer un contrôle qualité avant de prendre le chemin de l'imprimante.

Imprimez intelligemment.
Sauvez votre résine.
Méfiez-vous des hexagones.

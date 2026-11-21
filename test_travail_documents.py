"""
Tests de la modification d'un fichier joint (Word, Excel, PowerPoint) et du travail sur
les PDF (fusion, découpage, rotation, formulaire, tableaux), 21/11/2026.

Les fichiers sont de VRAIS documents fabriqués ici, lus et modifiés par les vraies
bibliothèques. Seuls les services distants (stockage, bibliothèque) sont simulés, dans
les tests de l'outil. Ces tests vérifient la logique, pas l'accord avec le stockage réel :
à confirmer sur staging avec un vrai fichier joint.
"""

import io
import sys

import pytest

sys.path.append("core")  # comme les autres tests

from core import modification_fichiers_office as office  # noqa: E402
from core import travail_pdf as pdf  # noqa: E402


# Fabrique de fichiers

def _docx():
    import docx

    document = docx.Document()
    document.add_heading("Rapport", level=1)
    paragraphe = document.add_paragraph()
    # Le mot est coupé en deux runs, comme Word le fait souvent après une correction.
    paragraphe.add_run("Bonjour Aw").bold = True
    paragraphe.add_run("a et bienvenue")
    document.add_paragraph("Fin du document")
    tableau = document.add_table(rows=1, cols=2)
    tableau.rows[0].cells[0].text = "Nom : Awa"
    tableau.rows[0].cells[1].text = "Note"
    document.sections[0].header.paragraphs[0].text = "En-tête pour Awa"
    flux = io.BytesIO()
    document.save(flux)
    return flux.getvalue()


def _textes_docx(octets):
    import docx

    document = docx.Document(io.BytesIO(octets))
    return [p.text for p in document.paragraphs], document


def _xlsx():
    import openpyxl

    classeur = openpyxl.Workbook()
    feuille = classeur.active
    feuille.title = "Notes"
    feuille.append(["nom", "note"])
    feuille.append(["Awa", 10])
    feuille.append(["Ibrahim", 14])
    feuille["D1"] = "=SUM(B2:B3)"
    flux = io.BytesIO()
    classeur.save(flux)
    return flux.getvalue()


def _charger_xlsx(octets):
    import openpyxl

    return openpyxl.load_workbook(io.BytesIO(octets))


def _pptx():
    from pptx import Presentation

    presentation = Presentation()
    for titre in ("Introduction", "Cours", "Conclusion"):
        diapositive = presentation.slides.add_slide(presentation.slide_layouts[1])
        diapositive.shapes.title.text = titre
        diapositive.placeholders[1].text_frame.text = f"Texte de {titre} sur Awa"
    flux = io.BytesIO()
    presentation.save(flux)
    return flux.getvalue()


def _titres_pptx(octets):
    from pptx import Presentation

    return [d.shapes.title.text for d in Presentation(io.BytesIO(octets)).slides]


def _pdf(textes_par_page):
    import fitz

    document = fitz.open()
    for texte in textes_par_page:
        page = document.new_page()
        page.insert_text((72, 72), texte)
    octets = document.tobytes()
    document.close()
    return octets


def _nb_pages(octets):
    return pdf.nombre_de_pages(octets)


# Word

class TestWord:
    def test_remplace_un_texte_coupe_entre_deux_runs_partout(self):
        nouveau, comptes = office.modifier_fichier_office(
            "docx", _docx(), [{"action": "remplacer_texte", "chercher": "Awa", "remplacer": "Fatou"}]
        )
        paragraphes, document = _textes_docx(nouveau)
        assert "Bonjour Fatou et bienvenue" in paragraphes
        assert document.tables[0].rows[0].cells[0].text == "Nom : Fatou"
        assert document.sections[0].header.paragraphs[0].text == "En-tête pour Fatou"
        assert "3 fois" in comptes[0]

    def test_la_mise_en_forme_du_run_de_depart_est_gardee(self):
        nouveau, _ = office.modifier_fichier_office(
            "docx", _docx(), [{"action": "remplacer_texte", "chercher": "Awa", "remplacer": "Fatou"}]
        )
        _, document = _textes_docx(nouveau)
        paragraphe = next(p for p in document.paragraphs if "Bonjour" in p.text)
        assert paragraphe.runs[0].bold is True

    def test_texte_introuvable_donne_une_erreur_claire_avec_le_numero(self):
        with pytest.raises(office.ErreurOperation, match="opération 1 .* introuvable"):
            office.modifier_fichier_office("docx", _docx(), [{"action": "remplacer_texte", "chercher": "zzz", "remplacer": "a"}])

    def test_ajouter_paragraphe_apres_un_texte_precis(self):
        nouveau, _ = office.modifier_fichier_office(
            "docx", _docx(), [{"action": "ajouter_paragraphe", "texte": "Ajout", "apres": "Rapport"}]
        )
        paragraphes, _ = _textes_docx(nouveau)
        assert paragraphes.index("Ajout") == paragraphes.index("Rapport") + 1

    def test_ajouter_paragraphe_a_la_fin_par_defaut(self):
        nouveau, _ = office.modifier_fichier_office("docx", _docx(), [{"action": "ajouter_paragraphe", "texte": "Ajout"}])
        paragraphes, _ = _textes_docx(nouveau)
        assert paragraphes[-1] == "Ajout"

    def test_ajouter_titre_et_niveau_invalide(self):
        nouveau, _ = office.modifier_fichier_office("docx", _docx(), [{"action": "ajouter_titre", "texte": "Partie 2", "niveau": 2}])
        _, document = _textes_docx(nouveau)
        assert document.paragraphs[-1].text == "Partie 2" and document.paragraphs[-1].style.name == "Heading 2"
        with pytest.raises(office.ErreurOperation, match="niveau"):
            office.modifier_fichier_office("docx", _docx(), [{"action": "ajouter_titre", "texte": "x", "niveau": 7}])

    def test_supprimer_un_paragraphe(self):
        nouveau, _ = office.modifier_fichier_office("docx", _docx(), [{"action": "supprimer_paragraphe", "contenant": "Fin du"}])
        paragraphes, _ = _textes_docx(nouveau)
        assert "Fin du document" not in paragraphes

    def test_ajouter_un_tableau(self):
        nouveau, _ = office.modifier_fichier_office(
            "docx", _docx(),
            [{"action": "ajouter_tableau", "en_tetes": ["A", "B"], "lignes": [[1, 2], [3, None]]}],
        )
        _, document = _textes_docx(nouveau)
        dernier = document.tables[-1]
        assert [c.text for c in dernier.rows[0].cells] == ["A", "B"]
        assert [c.text for c in dernier.rows[2].cells] == ["3", ""]

    def test_une_erreur_au_milieu_ne_livre_rien(self):
        with pytest.raises(office.ErreurOperation, match="opération 2"):
            office.modifier_fichier_office(
                "docx", _docx(),
                [{"action": "ajouter_paragraphe", "texte": "ok"}, {"action": "inconnue"}],
            )

    def test_l_original_n_est_pas_modifie(self):
        original = _docx()
        copie = bytes(original)
        office.modifier_fichier_office("docx", original, [{"action": "ajouter_paragraphe", "texte": "x"}])
        assert original == copie


# Excel

class TestExcel:
    def test_cellule_ligne_colonne_et_formule_existante_gardee(self):
        nouveau, _ = office.modifier_fichier_office(
            "xlsx", _xlsx(),
            [
                {"action": "definir_cellule", "cellule": "b2", "valeur": 12},
                {"action": "ajouter_ligne", "valeurs": ["Mariam", 16]},
                {"action": "ajouter_colonne", "en_tete": "rang", "valeurs": [1, 2, 3, 4]},
                {"action": "definir_cellule", "cellule": "D2", "valeur": "=B2*2"},
            ],
        )
        feuille = _charger_xlsx(nouveau)["Notes"]
        assert feuille["B2"].value == 12
        assert feuille["A4"].value == "Mariam"
        assert feuille["E1"].value == "rang" and feuille["E4"].value == 3
        assert feuille["D1"].value == "=SUM(B2:B3)"  # la formule d'origine est intacte
        assert feuille["D2"].value == "=B2*2"

    def test_supprimer_ligne_et_feuilles(self):
        nouveau, _ = office.modifier_fichier_office(
            "xlsx", _xlsx(),
            [
                {"action": "supprimer_ligne", "numero": 2},
                {"action": "ajouter_feuille", "nom": "Bilan"},
                {"action": "renommer_feuille", "feuille": "Notes", "nouveau_nom": "Notes finales"},
            ],
        )
        classeur = _charger_xlsx(nouveau)
        assert classeur.sheetnames == ["Notes finales", "Bilan"]
        assert classeur["Notes finales"]["A2"].value == "Ibrahim"

    @pytest.mark.parametrize("operation, motif", [
        ({"action": "definir_cellule", "cellule": "1A", "valeur": 1}, "adresse"),
        ({"action": "definir_cellule", "feuille": "Nulle part", "cellule": "A1", "valeur": 1}, "n'existe pas"),
        ({"action": "ajouter_feuille", "nom": "Budget : 2026"}, "ne peut pas contenir"),
        ({"action": "ajouter_feuille", "nom": "Notes"}, "existe déjà"),
        ({"action": "supprimer_ligne", "numero": 99}, "lignes"),
    ])
    def test_erreurs_claires(self, operation, motif):
        with pytest.raises(office.ErreurOperation, match=motif):
            office.modifier_fichier_office("xlsx", _xlsx(), [operation])


# PowerPoint

class TestPowerPoint:
    def test_remplacer_ajouter_supprimer_et_notes(self):
        nouveau, _ = office.modifier_fichier_office(
            "pptx", _pptx(),
            [
                {"action": "remplacer_texte", "chercher": "Awa", "remplacer": "Fatou"},
                {"action": "ajouter_diapositive", "titre": "Résumé", "contenu": "L'essentiel", "position": 2},
                {"action": "supprimer_diapositive", "numero": 1},
                {"action": "modifier_notes", "numero": 1, "texte": "Parler lentement"},
            ],
        )
        from pptx import Presentation

        presentation = Presentation(io.BytesIO(nouveau))
        assert _titres_pptx(nouveau) == ["Résumé", "Cours", "Conclusion"]
        diapositives = list(presentation.slides)
        assert "Fatou" in diapositives[1].placeholders[1].text_frame.text
        assert diapositives[0].notes_slide.notes_text_frame.text == "Parler lentement"

    def test_numero_hors_limites(self):
        with pytest.raises(office.ErreurOperation, match="3 diapositives"):
            office.modifier_fichier_office("pptx", _pptx(), [{"action": "supprimer_diapositive", "numero": 9}])


def test_famille_non_modifiable_et_liste_vide():
    with pytest.raises(office.ErreurOperation, match="modifiables"):
        office.modifier_fichier_office("pdf", b"", [{"action": "x"}])
    with pytest.raises(office.ErreurOperation, match="vide"):
        office.modifier_fichier_office("docx", _docx(), [])


# PDF

class TestPdf:
    def test_plages(self):
        assert pdf.lire_plages("1-3, 5", 6) == [0, 1, 2, 4]
        assert pdf.lire_plages("4-", 6) == [3, 4, 5]
        assert pdf.lire_plages("-2", 6) == [0, 1]
        assert pdf.lire_plages("", 3) == [0, 1, 2]
        assert pdf.lire_plages("3,1", 3) == [2, 0]  # l'ordre demandé est gardé

    @pytest.mark.parametrize("texte", ["abc", "0", "5-2", "9"])
    def test_plages_invalides(self, texte):
        with pytest.raises(pdf.ErreurPdf):
            pdf.lire_plages(texte, 6)

    def test_fusion(self):
        octets, total = pdf.fusionner([_pdf(["a", "b"]), _pdf(["c"])])
        assert total == 3 and _nb_pages(octets) == 3

    def test_fusion_demande_au_moins_deux_pdf_et_refuse_un_fichier_illisible(self):
        with pytest.raises(pdf.ErreurPdf, match="au moins deux"):
            pdf.fusionner([_pdf(["a"])])
        with pytest.raises(pdf.ErreurPdf, match="illisible"):
            pdf.fusionner([_pdf(["a"]), b"pas un pdf"], ["un.pdf", "deux.pdf"])

    def test_fusion_refuse_un_pdf_protege(self):
        import fitz

        document = fitz.open()
        document.new_page()
        protege = document.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="x", user_pw="y")
        with pytest.raises(pdf.ErreurPdf, match="mot de passe"):
            pdf.fusionner([_pdf(["a"]), protege], ["a.pdf", "secret.pdf"])

    def test_decoupage_par_plages_et_par_taille(self):
        contenu = _pdf(["1", "2", "3", "4", "5"])
        morceaux = pdf.calculer_morceaux(5, plages=["1-2", "5"])
        assert [m[1] for m in morceaux] == [[0, 1], [4]]
        assert _nb_pages(pdf.extraire_pages(contenu, morceaux[0][1])) == 2
        regulier = pdf.calculer_morceaux(5, pages_par_morceau=2)
        assert [len(m[1]) for m in regulier] == [2, 2, 1]
        assert regulier[2][0] == "page 5"

    def test_decoupage_demande_une_consigne_et_borne_le_nombre_de_morceaux(self):
        with pytest.raises(pdf.ErreurPdf, match="plages"):
            pdf.calculer_morceaux(5)
        with pytest.raises(pdf.ErreurPdf, match="morceaux au plus"):
            pdf.calculer_morceaux(100, pages_par_morceau=1)

    def test_rotation(self):
        import fitz

        octets, tournees = pdf.tourner(_pdf(["a", "b", "c"]), 90, "2-3")
        assert tournees == 2
        document = fitz.open(stream=octets, filetype="pdf")
        assert [p.rotation for p in document] == [0, 90, 90]
        octets2, _ = pdf.tourner(octets, -90, "3")
        assert [p.rotation for p in fitz.open(stream=octets2, filetype="pdf")] == [0, 90, 0]

    @pytest.mark.parametrize("angle", [0, 45, "abc", 360])
    def test_rotation_angle_invalide(self, angle):
        with pytest.raises(pdf.ErreurPdf):
            pdf.tourner(_pdf(["a"]), angle)

    def _formulaire(self):
        import fitz

        document = fitz.open()
        page = document.new_page()
        texte = fitz.Widget()
        texte.field_name, texte.field_type = "Nom", fitz.PDF_WIDGET_TYPE_TEXT
        texte.rect = fitz.Rect(72, 72, 300, 100)
        page.add_widget(texte)
        case = fitz.Widget()
        case.field_name, case.field_type = "Accepte", fitz.PDF_WIDGET_TYPE_CHECKBOX
        case.rect = fitz.Rect(72, 120, 90, 138)
        page.add_widget(case)
        octets = document.tobytes()
        document.close()
        return octets

    def test_lister_et_remplir_un_formulaire(self):
        import fitz

        contenu = self._formulaire()
        champs = pdf.lister_champs(contenu)
        assert {(c["nom"], c["type"]) for c in champs} == {("Nom", "Text"), ("Accepte", "CheckBox")}

        octets, remplis, introuvables = pdf.remplir_formulaire(contenu, {"nom": "Awa Traoré", "Accepte": True, "Inconnu": "x"})
        assert sorted(remplis) == ["Accepte", "Nom"] and introuvables == ["Inconnu"]
        document = fitz.open(stream=octets, filetype="pdf")
        valeurs = {w.field_name: w.field_value for w in document[0].widgets()}
        assert valeurs["Nom"] == "Awa Traoré"
        assert valeurs["Accepte"] not in ("Off", "", False, None)

    def test_formulaire_erreurs(self):
        with pytest.raises(pdf.ErreurPdf, match="aucun champ de formulaire"):
            pdf.remplir_formulaire(_pdf(["à plat"]), {"Nom": "x"})
        with pytest.raises(pdf.ErreurPdf, match="Champs disponibles"):
            pdf.remplir_formulaire(self._formulaire(), {"Inconnu": "x"})
        with pytest.raises(pdf.ErreurPdf, match="aucune valeur"):
            pdf.remplir_formulaire(self._formulaire(), {})

    def _pdf_avec_tableau(self):
        import fitz

        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 60), "Resultats de la classe")
        x0, y0, largeur, hauteur = 72, 100, 120, 28
        lignes = [["Nom", "Note"], ["Awa", "17"], ["Ibrahim", "12"]]
        for i, ligne in enumerate(lignes):
            for j, cellule in enumerate(ligne):
                rect = fitz.Rect(x0 + j * largeur, y0 + i * hauteur, x0 + (j + 1) * largeur, y0 + (i + 1) * hauteur)
                page.draw_rect(rect, color=(0, 0, 0), width=1)
                page.insert_text((rect.x0 + 6, rect.y0 + 19), cellule)
        document.new_page().insert_text((72, 72), "Page sans tableau")
        scan = document.new_page()  # page sans aucun texte natif
        octets = document.tobytes()
        document.close()
        return octets

    def test_lire_les_tableaux_en_markdown(self):
        resultat = pdf.lire_tableaux(self._pdf_avec_tableau(), 1, 2, 30000, 15)
        assert "Page 1, tableau 1" in resultat
        assert "| Nom | Note |" in resultat and "| Awa | 17 |" in resultat

    def test_tableaux_previent_pour_une_page_sans_texte(self):
        resultat = pdf.lire_tableaux(self._pdf_avec_tableau(), 3, 3, 30000, 15)
        assert "sans texte natif" in resultat and "Aucun tableau" in resultat

    def test_tableaux_page_hors_limites_et_lecture_partielle(self):
        assert "n'existe pas" in pdf.lire_tableaux(self._pdf_avec_tableau(), 9, 9, 30000, 15)
        partiel = pdf.lire_tableaux(self._pdf_avec_tableau(), 1, 3, 30000, 1)
        assert "Lecture partielle" in partiel and "debut_page=2" in partiel

"""
Endpoint de lecture de l'audit complet du Bureau (20/09/2026, demande
Bourama) -- tableau de bord d'un code de partage, voir
core/audit_complet_bureau.py. Séparé de api/audit_hebdomadaire_corrections.py
(audit hebdomadaire des signalements, brique de logique distincte,
même règle que le fichier existant).
"""

from fastapi import APIRouter, Depends

from api.auth import utilisateur_courant
from core.audit_complet_bureau import calculer_audit_complet

router = APIRouter(prefix="/api/audit-complet", tags=["audit_complet_bureau"])


@router.get("/{code_id}")
def audit_complet(code_id: str, utilisateur=Depends(utilisateur_courant)):
    """Tableau de bord complet d'un des codes du prof courant (voir
    Bureau > Audit). 404 si le code n'existe pas ou n'appartient pas à
    l'utilisateur courant (jamais de distinction entre les deux, pour ne
    rien laisser fuiter sur l'existence d'un code d'un autre prof)."""
    return calculer_audit_complet(utilisateur.id, code_id)

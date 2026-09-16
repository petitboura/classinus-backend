"""
Module partagé de connexion au stockage Cloudflare R2, remplaçant
progressivement Supabase Storage (voir les chantiers de migration
liés, étapes 2 à 5).

Reproduit volontairement la même interface que
`supabase.storage.from_(BUCKET)` (upload/download/remove/get_public_url)
pour que les fichiers appelants n'aient, à terme, qu'à remplacer
`supabase.storage.from_(BUCKET)` par `stockage_r2.from_(BUCKET)`, sans
changer leur logique.

Un seul bucket R2 existe (variable R2_BUCKET_NAME, posée sur Railway) :
les anciens "buckets" Supabase (bibliotheque, images-publiques,
generations, documents-agents) deviennent des préfixes de clé à
l'intérieur de ce bucket unique (ex. clé "bibliotheque/xxx.pdf" pour
un chemin "xxx.pdf" dans le bucket logique "bibliotheque").

Sécurité : le bucket R2 reste privé (comportement par défaut de R2,
aucun accès public direct). get_public_url() ne renvoie donc PAS une
URL R2 directe, mais une URL de ce même backend (route définie dans
api/fichiers_r2.py) qui va chercher l'objet dans R2 et le sert. Deux
raisons à ce choix plutôt qu'un accès public direct :
  - aucun domaine personnalisé n'est aujourd'hui branché sur le bucket
    côté Cloudflare (ça demanderait de posséder une zone DNS sur
    Cloudflare, à configurer manuellement dans le dashboard) ;
  - l'URL de développement r2.dev (alternative sans domaine) est
    explicitement déconseillée par Cloudflare pour de la production
    (pas faite pour absorber du vrai trafic, taux de requêtes limité).
Si un domaine personnalisé est branché plus tard sur le bucket, il
suffira de poser la variable R2_PUBLIC_BASE_URL sur ce domaine pour
que get_public_url() y pointe directement, sans toucher au reste du
code ni aux URLs déjà stockées en base (même forme d'URL, juste servie
différemment en coulisses si on veut plus tard basculer la route
elle-même en redirection au lieu d'un relais).
"""

import logging
import os

import boto3
from botocore.config import Config


def _get_secret(cle):
    return os.environ.get(cle)


R2_ENDPOINT = _get_secret("R2_ENDPOINT")
R2_ACCESS_KEY_ID = _get_secret("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = _get_secret("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = _get_secret("R2_BUCKET_NAME")

# Base publique des URLs renvoyées par get_public_url(). Par défaut, ce
# backend lui-même (voir api/fichiers_r2.py). RAILWAY_PUBLIC_DOMAIN est
# posée automatiquement par Railway sur chaque service exposé.
R2_PUBLIC_BASE_URL = _get_secret("R2_PUBLIC_BASE_URL") or (
    f"https://{_get_secret('RAILWAY_PUBLIC_DOMAIN')}" if _get_secret("RAILWAY_PUBLIC_DOMAIN") else None
)

_client = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    config=Config(signature_version="s3v4"),
    region_name="auto",
)


def _cle_objet(bucket_logique: str, chemin: str) -> str:
    return f"{bucket_logique}/{chemin}"


class _BucketLogique:
    """
    Objet renvoyé par from_(bucket_logique). Reproduit l'API de
    supabase.storage.from_(BUCKET) : upload, download, remove,
    get_public_url.
    """

    def __init__(self, bucket_logique: str):
        self._bucket_logique = bucket_logique

    def upload(self, chemin: str, contenu: bytes, file_options: dict | None = None):
        """
        Équivalent de supabase.storage.from_(BUCKET).upload(chemin, contenu, file_options).
        file_options peut contenir "content-type" (comme côté Supabase).
        """
        extra_args = {}
        if file_options:
            type_contenu = file_options.get("content-type") or file_options.get("contentType")
            if type_contenu:
                extra_args["ContentType"] = type_contenu
        try:
            _client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=_cle_objet(self._bucket_logique, chemin),
                Body=contenu,
                **extra_args,
            )
        except Exception as e:
            logging.error(f"ERREUR R2 STORAGE (upload {self._bucket_logique}/{chemin}) : {e}")
            raise

    def download(self, chemin: str) -> bytes:
        """Équivalent de supabase.storage.from_(BUCKET).download(chemin)."""
        try:
            reponse = _client.get_object(
                Bucket=R2_BUCKET_NAME,
                Key=_cle_objet(self._bucket_logique, chemin),
            )
            return reponse["Body"].read()
        except Exception as e:
            logging.error(f"ERREUR R2 STORAGE (download {self._bucket_logique}/{chemin}) : {e}")
            raise

    def remove(self, chemins: list[str]):
        """Équivalent de supabase.storage.from_(BUCKET).remove([chemin, ...])."""
        if not chemins:
            return
        objets = [{"Key": _cle_objet(self._bucket_logique, chemin)} for chemin in chemins]
        try:
            _client.delete_objects(Bucket=R2_BUCKET_NAME, Delete={"Objects": objets})
        except Exception as e:
            logging.error(f"ERREUR R2 STORAGE (remove {self._bucket_logique}/{chemins}) : {e}")
            raise

    def get_public_url(self, chemin: str) -> str:
        """
        Équivalent de supabase.storage.from_(BUCKET).get_public_url(chemin) :
        renvoie une chaîne d'URL utilisable telle quelle, sans expiration.
        Voir la note de sécurité en tête de fichier.
        """
        base = R2_PUBLIC_BASE_URL or ""
        return f"{base}/fichiers/r2/{self._bucket_logique}/{chemin}"


def from_(bucket_logique: str) -> _BucketLogique:
    return _BucketLogique(bucket_logique)

# Extrait de main.py le 05/09/2026 (demande Bourama : diviser les fichiers
# trop longs). Sauvegarde d'un echange (message + reponse) et mise a jour
# periodique du profil utilisateur par agent.
import logging
import threading
from constantes_agent import supabase
from profils_agents import _mettre_a_jour_profil_utilisateur_si_besoin

def _parent_effectif(user_id, agent_id, conversation_id, parent_id):
    """
    Parent reel de la prochaine ligne "user" d'un fil (31/10/2026, bug
    remonte par Bourama : dernier echange invisible a la reouverture).

    Le frontend envoie parent_id=None quand sa liste locale ne contient
    encore aucun message deja enregistre (reouverture, reprise de flux,
    conversation partagee...) alors que le fil a deja des lignes en base.
    Inserer tel quel cree une deuxieme racine : a la reouverture, le
    frontend traite les racines comme des versions alternatives du
    premier message et n'affiche qu'une branche, l'echange le plus
    recent peut donc disparaitre de l'ecran sans etre perdu en base.

    Regle : dans un fil qui a deja des lignes, un parent absent,
    introuvable dans CE fil, ou de role "user" est repare sur la
    derniere ligne du fil. Une nouvelle question suit toujours une
    reponse : rattachee a une question, elle deviendrait la soeur de la
    reponse de cette question, et le frontend les lirait comme des
    versions alternatives (voir les freres de roles differents releves
    le 31/10/2026). Un parent "assistant" present dans le fil est
    respecte tel quel, meme ancien : c'est le cas legitime d'une
    branche (message edite, version).

    Sans conversation_id, le fil est le groupe "legacy" du meme
    utilisateur et du meme agent (conversation_id NULL en base, affiche
    comme un seul fil cote historique) : meme reparation, partitionnee
    sur ce groupe, plutot que de recreer une racine a chaque echange.
    """
    def _dans_le_fil(requete):
        requete = requete.eq("user_id", user_id).eq("agent_id", agent_id)
        if conversation_id:
            return requete.eq("conversation_id", conversation_id)
        return requete.is_("conversation_id", "null")

    try:
        if parent_id is not None:
            res_parent = (
                _dans_le_fil(supabase.table("historique_conversations").select("id, role"))
                .eq("id", parent_id)
                .limit(1)
                .execute()
            )
            parents = res_parent.data or []
            if parents and parents[0].get("role") == "assistant":
                return parent_id
        res_derniere = (
            _dans_le_fil(supabase.table("historique_conversations").select("id"))
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        lignes = res_derniere.data or []
        if not lignes:
            return None
        parent_repare = lignes[0]["id"]
        if parent_id != parent_repare:
            logging.warning(
                "parent_id repare dans historique_conversations "
                f"(conversation_id={conversation_id}, recu={parent_id}, utilise={parent_repare})"
            )
        return parent_repare
    except Exception as e:
        # La reparation ne doit jamais empecher la sauvegarde elle-meme :
        # en cas d'echec de lecture, on retente avec le parent recu.
        logging.error(f"ERREUR SUPABASE (verification parent historique) : {e}")
        return parent_id


def _sauvegarder_echange(user_id, agent_id, message_utilisateur, reponse_finale, conversation_id=None, modele=None, meta_utilisateur=None, meta_assistant=None, parent_id=None, sauvegarder_message_utilisateur=True):
    """
    Persiste l'echange (question + reponse) dans `conversations`, pour la
    memoire long-terme. Ignore silencieusement si l'utilisateur n'est pas
    connecte (user_id=None) ou si la reponse est vide (ex: message
    d'erreur technique, qu'on ne veut pas polluer la memoire avec).

    `modele` (optionnel, 02/08/2026) : modele_id qui a genere
    `reponse_finale`, ecrit UNIQUEMENT sur la ligne "assistant" de
    `historique_conversations` (pas sur `conversations`, table de memoire
    court terme sans vocation d'affichage) -- None si la cascade Groq/
    Gemini par defaut a repondu (comportement historique inchange, colonne
    nullable), sinon le modele_id premium (voir core/fournisseurs_llm.py).
    Permet au frontend d'afficher quel modele a repondu sous chaque
    message (voir AgentEditable.modeles_disponibles cote api/agents.py).

    `meta_utilisateur`/`meta_assistant` (optionnels, dict, 28/08/2026) :
    ecrits respectivement sur la ligne "user" et la ligne "assistant" de
    historique_conversations (colonne meta, jsonb). But : ce qui n'existe
    aujourd'hui que le temps du direct (evenements SSE outil_resultat/
    sources, piece jointe image) disparaissait entierement a la
    reouverture d'une conversation, seul le texte brut survivant. Contenu
    attendu : meta_utilisateur = {"pieces_jointes": [...]},
    meta_assistant = {"outils": [{"nomOutil", "nomLisible", "resultat",
    "sources"}, ...], "segments": [...]} -- voir _capturer_reponse pour la
    construction de meta_assistant. "outils" est aligne sur
    MessageAffiche.outilsResultats cote frontend (affichage groupe,
    ancien format) ; "segments" (ajoute le 15/09/2026, demande Bourama)
    est la timeline chronologique complete (raisonnement/texte/outil dans
    l'ordre reel), alignee sur MessageAffiche.segments -- permet de
    reconstruire a la reouverture le meme affichage qu'en direct, plutot
    que l'ancien rendu groupe approximatif. Absent pour les echanges
    anterieurs a cette date (pas de retro-remplissage).

    `parent_id`/`sauvegarder_message_utilisateur` (ajoutes le 20/09/2026,
    chantier "versions navigables", voir la migration
    2026_09_20c_versions_navigables_historique.sql) : ecrits UNIQUEMENT
    sur historique_conversations (colonne parent_id), jamais sur
    `conversations` (table de memoire court terme sans notion de
    version). Deux cas :
    - sauvegarder_message_utilisateur=True (comportement par defaut,
      inchange) : `parent_id` est le parent_id de la ligne "user" creee
      ici (id de la derniere ligne de la branche precedente, None si
      c'est le tout premier message de la conversation). La ligne
      "assistant" creee juste apres prend pour parent l'id auto-genere
      (bigint identity Postgres, PAS un uuid) de cette ligne "user",
      necessite donc DEUX inserts sequentiels (impossible de connaitre
      l'id avant que Postgres l'attribue), contrairement a l'ancien
      insert groupe des deux lignes en un seul aller-retour.
    - sauvegarder_message_utilisateur=False ("reessayer", voir
      core/main.py:chat() parametre `regenerer`) : AUCUNE ligne "user"
      n'est creee (ni ici ni dans `conversations`, la question existe
      deja depuis la premiere tentative), `parent_id` est directement
      l'id de cette ligne "user" EXISTANTE, et la nouvelle ligne
      "assistant" devient une VERSION ALTERNATIVE (meme parent_id que
      l'ancienne reponse) plutot qu'une suite.
    """
    ids_historique = None  # renvoyé à l'appelant pour l'indexation du feedback

    if not user_id or not (reponse_finale or "").strip():
        return ids_historique

    if sauvegarder_message_utilisateur:
        try:
            supabase.table("conversations").insert([
                {"user_id": user_id, "agent_id": agent_id, "role": "user", "content": message_utilisateur},
                {"user_id": user_id, "agent_id": agent_id, "role": "assistant", "content": reponse_finale},
            ]).execute()
        except Exception as e:
            logging.error(f"ERREUR SUPABASE (sauvegarde conversations) : {e}")
    # sauvegarder_message_utilisateur=False ("reessayer") : rien a ajouter
    # dans `conversations`, la question a deja ete enregistree la premiere
    # fois, dupliquer la question sans la reponse casserait la paire
    # user/assistant que cette table suppose toujours alternee.

    # Ajouté le 2026-07-13 (Bourama : historique de conversation visible,
    # conservée par agent, dans le tableau de bord). Table SÉPARÉE de
    # `conversations` ci-dessus, jamais purgée -- voir le commentaire de
    # migration (historique_conversations) pour le detail de la
    # distinction. Volontairement dans un bloc try/except À PART : si cette
    # écriture échoue, ça ne doit jamais faire échouer la mémoire de l'IA
    # ci-dessus, qui est la partie critique pour la qualité des réponses.
    #
    # `conversation_id` (2026-07-13, Bourama : liste de conversations
    # distinctes et cliquables dans la sidebar de chat.py, façon Claude.ai)
    # regroupe les messages d'un même fil de discussion, généré côté
    # chat.py (une valeur par conversation affichée, PAS par message) et
    # simplement transmis ici tel quel. None accepté (colonne nullable) :
    # un appelant qui ne gère pas encore les fils continue de fonctionner
    # sans erreur, ses messages sont juste groupés sous "historique ancien"
    # côté affichage plutôt que dans un fil précis.
    #
    # Chantier "versions navigables" (20/09/2026) : `id` de cette table
    # est un bigint IDENTITY Postgres (pas un uuid), impossible a deviner
    # cote Python avant l'insertion, quand sauvegarder_message_utilisateur
    # est vrai, DEUX inserts sequentiels sont donc necessaires (la ligne
    # "user" doit exister, avec son id reellement attribue par Postgres,
    # avant de pouvoir inserer la ligne "assistant" qui la reference comme
    # parent_id). Un seul insert groupe suffit dans le cas contraire
    # (reessayer), puisque le parent (la question existante) est deja
    # connu.
    try:
        # Reparation d'un parent absent/introuvable (voir _parent_effectif) :
        # uniquement pour une nouvelle ligne "user". En mode reessayer, le
        # parent designe la question existante et doit rester tel quel,
        # sinon la nouvelle reponse ne serait plus une version alternative.
        parent_effectif = (
            _parent_effectif(user_id, agent_id, conversation_id, parent_id)
            if sauvegarder_message_utilisateur
            else parent_id
        )
        id_parent_assistant = parent_effectif
        if sauvegarder_message_utilisateur:
            res_user = (
                supabase.table("historique_conversations")
                .insert({
                    "user_id": user_id, "agent_id": agent_id, "role": "user", "content": message_utilisateur,
                    "conversation_id": conversation_id, "meta": meta_utilisateur or None, "parent_id": parent_effectif,
                })
                .execute()
            )
            lignes_user = res_user.data or []
            if not lignes_user:
                raise RuntimeError("insertion de la ligne 'user' sans retour de ligne")
            id_parent_assistant = lignes_user[0]["id"]

        res_assistant = (
            supabase.table("historique_conversations")
            .insert({
                "user_id": user_id, "agent_id": agent_id, "role": "assistant", "content": reponse_finale,
                "conversation_id": conversation_id, "modele": modele, "meta": meta_assistant or None,
                "parent_id": id_parent_assistant,
            })
            .execute()
        )
        lignes_assistant = res_assistant.data or []
        if lignes_assistant:
            ligne_assistant = lignes_assistant[0]
            ids_historique = {
                # Reessayer (sauvegarder_message_utilisateur=False) : pas
                # de nouvelle ligne "user" cree ici, message_id_user reste
                # donc l'id de la ligne "user" EXISTANTE (recu via
                # `parent_id`), toujours une vraie valeur utilisable cote
                # frontend, jamais None dans ce cas.
                "message_id_user": id_parent_assistant if sauvegarder_message_utilisateur else parent_id,
                "message_id_assistant": ligne_assistant["id"],
                "created_at_assistant": ligne_assistant.get("created_at"),
                # Propage automatiquement dans tous les evenements SSE
                # "meta" (voir chaque site d'appel plus haut, tous font
                # **ids_historique) -- evite de dupliquer ce champ a la
                # main partout, voir ChatIA.tsx cote frontend pour l'usage.
                "modele": modele,
            }
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (sauvegarde historique_conversations) : {e}")

    return ids_historique


def _finaliser_memoire_en_arriere_plan(user_id, agent_id):
    """
    Lance _mettre_a_jour_profil_utilisateur_si_besoin en tache de fond,
    SANS attendre son resultat (11/09/2026, demande Bourama : "rien qui
    retarde ne serait-ce que d'une milliseconde la reponse de l'IA").
    Cette mise a jour ne concerne jamais la reponse deja affichee a
    l'instant meme, elle prepare seulement le profil pour les PROCHAINS
    messages. Avant ce fix, chat() attendait cet appel (une lecture en
    base systematique, parfois un appel Groq complet en plus) avant de
    considerer l'echange termine, ce qui retardait la disponibilite des
    identifiants de message (evenement "meta", necessaires aux boutons
    like/dislike) sans aucune raison liee a CE message-ci.

    La memoire de l'eleve n'est plus mise a jour ici : c'est le modele
    lui-meme qui l'ecrit pendant la conversation (core/outils_memoire_eleve.py).

    Fire-and-forget assume : toute erreur reste loguee a l'interieur de la
    fonction elle-meme, jamais remontee ici ni a l'appelant.
    """
    def _tache():
        try:
            _mettre_a_jour_profil_utilisateur_si_besoin(user_id, agent_id)
        except Exception as e:
            logging.error(f"ERREUR tache de fond (profil utilisateur) : {e}")

    threading.Thread(target=_tache, daemon=True).start()

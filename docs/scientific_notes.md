# Note on scientific articles

Articles étudiés :

- Gottweis et al., Nature 2026
- Ghareeb et al., Nature 2026

---

## 1. Co-Scientist

### Idées

- Système multi-agents asynchrone basé sur Gemini coordoné par un agent *Supervisor* et une mémoire contextuelle persistante.

- **Hypothèses Self-Play**: Les agents émettent des hypothèses et les soumettent à des débats simulés. Elles sont ensuite classées via un tournoi type *Elo*.

### Critiques

- Même l'IA de Google bute sur des articles cachés derrière un paywall.
- Propage les biais de littérature s'il n'y a pas de contrôle humain strict

- Risque d'homogénéisation & baisse de rigueur
  => Dégrade la reproductibilité scientifique.

- Nécessite une infrastructure massive pour l'hébergement et le code source est fermé.

---

## 2.Robin

### Idées

- Architecyure semo-autonome (*lab-in-the-loop*) combinant deux agents bibliographiques (Crow & Falcon) et un agent d'analyse de données (Finch).

- Cycle itératif en deux phases:
  - Génération et classement d'hypopothèses par comparaisons par paires.
  - Analyse bioinformatique sur des données réelles.

### Critiques

- Dimensionné pour brasser 550 particles et générer 30 candidats thérapeutiques d'un coup => Coûte environ $10 pour un seul run.
- Même leur agent d'analyse Finch échoue sur 85% des cas lors d'une variation de paramètres très précise.

- Conclusion des auteurs: "Les architectures dédiées au domaine restent indispensables pur imposer des contraintes expérimentales"

- L'équipe de FutureHouse a abandonné le modèle non-déterministe agentique au profit d'une architecture détemriniste pour garantir la stabilité et maintenabilité.

---

## À retenir

1. **Séparation lecture rapide vs. approfondie**: Inpirée de Crow vs. Falcon dans Robin.

- Déjà amorcé dans `library` => le LLM local joue le rôle de Crow en filtrant rapidement les articles non relevent à moindre coûts.
- TODO -- Pour la phase 2 : Utiliser un modèle plus gros pour la phase d'ingestion des données et de construction des hypothèses (extraction des données techniques, etc...)

1. **Reflextion / Deep-verification** : Mettre en place un traçage des hypothèses pour pouvoir remonter à l'article source à chaque fois -> Prévient le phénomène d'hallucination.

- Décomposition des hypothèses en sous-affirmations testables ?

1. **Feedback Global**: Intégrer une structure enregistrant les précédents échecs méthodologiques / expérimentaux à réinjecter à la prochaine inférence.
  => Prévient le fine-tunning sans objectif clair.

2. **Script auditables** : Demander à l'agent de générer des scrips expérimentaux vérifiables par un humain plutôt qu'une liste de course à appliquer bêtement.

- Production d'une matrice comparative des paramètres utulisés dans les 50 papiers et des gabarits de scripts reproductibles déjà validés à la main sur le jeu de données.

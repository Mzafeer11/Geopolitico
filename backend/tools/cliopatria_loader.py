import json
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional
from backend.config import DATA_DIR

DEFAULT_FILE = DATA_DIR / "cliopatria_polities_only.geojson"

def normalize_name(s: str) -> str:
    """Normalize names for case-insensitive, accent-free matching."""
    if not s:
        return ""
    # Strip parentheses and brackets
    s = s.replace("(", "").replace(")", "").replace("[", "").replace("]", "")
    nfkd = unicodedata.normalize("NFKD", s)
    s_clean = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    return " ".join(s_clean.replace("-", " ").replace("_", " ").split())

def is_subphrase(sub: str, main: str) -> bool:
    """Check if a sequence of words 'sub' appears consecutively in 'main' as whole words."""
    sub_words = sub.split()
    main_words = main.split()
    if not sub_words or not main_words:
        return False
    for i in range(len(main_words) - len(sub_words) + 1):
        if main_words[i:i+len(sub_words)] == sub_words:
            return True
    return False

def get_core_name(s: str) -> str:
    """Extract the core polity name by removing common geopolitical qualifiers."""
    norm = normalize_name(s)
    qualifiers = [
        "republic of", "dominion of", "islamic republic of", "kingdom of", 
        "empire of", "caliphate of", "united", "federation of", "sultanate of",
        "caliphate", "empire", "kingdom", "republic", "dominion", "sultanate",
        "principality of", "principality", "grand duchy of", "duchy of", "duchy"
    ]
    for q in qualifiers:
        if norm.startswith(q + " "):
            norm = norm[len(q) + 1:].strip()
        if norm.endswith(" " + q):
            norm = norm[:-len(q) - 1].strip()
    return norm


class CliopatriaDatabase:

    _instance: Optional["CliopatriaDatabase"] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(CliopatriaDatabase, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, file_path: Path = DEFAULT_FILE):
        if self._initialized:
            return
        self.file_path = Path(file_path)
        self.features: List[Dict[str, Any]] = []
        
        # Indexes for O(1) / O(log N) lookups
        self.by_normalized_name: Dict[str, List[Dict[str, Any]]] = {}
        self.active_by_year_cache: Dict[int, List[Dict[str, Any]]] = {}
        
        self._initialized = True

    def _ensure_loaded(self):
        """Lazily load the GeoJSON file on first use to speed up server start."""
        if self.features:
            return
        
        if not self.file_path.exists():
            raise FileNotFoundError(f"Cliopatria GeoJSON file not found at {self.file_path}")
            
        print(f"[CLIOPATRIA] Loading {self.file_path.name} ({self.file_path.stat().st_size/1024/1024:.2f} MB)...")
        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.features = data.get("features", [])
        print(f"[CLIOPATRIA] Loaded {len(self.features)} features.")
        
        # Build index
        for f in self.features:
            props = f.get("properties", {})
            name = props.get("Name") or ""
            if name:
                norm = normalize_name(name)
                self.by_normalized_name.setdefault(norm, []).append(f)
                
        print(f"[CLIOPATRIA] Indexed {len(self.by_normalized_name)} unique polity names.")

    def get_active_polities(self, year: int) -> List[Dict[str, Any]]:
        """Get all polities active during the target year."""
        self._ensure_loaded()
        
        if year in self.active_by_year_cache:
            return self.active_by_year_cache[year]
            
        active = []
        for f in self.features:
            props = f.get("properties", {})
            from_yr = props.get("FromYear")
            to_yr = props.get("ToYear")
            if from_yr is not None and to_yr is not None:
                if from_yr <= year <= to_yr:
                    active.append(f)
                    
        self.active_by_year_cache[year] = active
        return active

    def get_polity_geometry(self, name: str, year: int) -> Optional[Dict[str, Any]]:
        """
        Get the geometry snapshot for a given polity name at the target year.
        If no exact snapshot covers the year, fall back to historical epoch aliases/core names active in the target year,
        and finally to the closest snapshot in time.
        """
        self._ensure_loaded()
        
        norm = normalize_name(name)
        
        target_year = year
        if year == 1947 and norm in ("india", "republic of india", "pakistan", "islamic republic of pakistan"):
            # In Cliopatria, 1947 is a temporary 2-month transitional snapshot (FromYear: 1947, ToYear: 1947)
            # where Hyderabad State and Jammu & Kashmir were isolated separate polygons, leaving
            # Republic of India with a hollow hole in the Deccan (Hyderabad) and missing Kashmir.
            # For general historical analysis and partition treaties of India/Pakistan in 1947,
            # resolve to the integrated 1948-1952 snapshot so Hyderabad and Kashmir are properly included.
            target_year = 1948
        
        def _expand_alias_and_core_candidates(target_list: List[Dict[str, Any]]):
            epoch_aliases = {
                "france": ["french third republic", "kingdom of france", "first french empire", "second french empire", "french fourth republic", "french fifth republic"],
                "germany": ["german empire", "weimar republic", "federal republic of germany"],
                "russia": ["russian empire", "union of soviet socialist republics", "ussr", "tsardom of russia"],
                "turkey": ["ottoman empire", "republic of turkey"],
                "iran": ["persia", "qajar iran", "pahlavi iran", "safavid iran"],
                "united kingdom": ["kingdom of great britain", "united kingdom of great britain and ireland"],
                "britain": ["kingdom of great britain", "united kingdom"],
                "spain": ["kingdom of spain", "spanish empire"],
                "italy": ["kingdom of italy"],
                "austria": ["habsburg monarchy", "austrian empire", "austria hungary"],
            }
            core_search = get_core_name(name)
            alias_norms = epoch_aliases.get(norm, []) + epoch_aliases.get(core_search, [])
            for a_norm in alias_norms:
                if a_norm in self.by_normalized_name:
                    target_list.extend(self.by_normalized_name[a_norm])
            for indexed_name, feats in self.by_normalized_name.items():
                if is_subphrase(norm, indexed_name) or is_subphrase(indexed_name, norm):
                    target_list.extend(feats)
                elif core_search and core_search == get_core_name(indexed_name):
                    target_list.extend(feats)

        # Collect all candidate features matching the name (exact first, then alias/substring/core name)
        all_candidate_feats = []
        if norm in self.by_normalized_name:
            all_candidate_feats.extend(self.by_normalized_name[norm])
        else:
            _expand_alias_and_core_candidates(all_candidate_feats)
                        
        if not all_candidate_feats:
            return None
            
        # 1. Look for candidates active in the target year
        active_candidates = []
        for feat in all_candidate_feats:
            props = feat.get("properties", {})
            from_yr = props.get("FromYear")
            to_yr = props.get("ToYear")
            if from_yr is not None and to_yr is not None:
                if from_yr <= target_year <= to_yr:
                    active_candidates.append(feat)

        # 1b. If exact match had no active candidates in `target_year` (e.g. 'France' or 'Germany' in 1919),
        # check historical epoch aliases and core-name matches active in `target_year`.
        if not active_candidates:
            expanded_feats: List[Dict[str, Any]] = []
            _expand_alias_and_core_candidates(expanded_feats)
            for feat in expanded_feats:
                props = feat.get("properties", {})
                from_yr = props.get("FromYear")
                to_yr = props.get("ToYear")
                if from_yr is not None and to_yr is not None and (from_yr <= target_year <= to_yr):
                    active_candidates.append(feat)
            if not active_candidates and expanded_feats:
                all_candidate_feats.extend(expanded_feats)
                    
        if active_candidates:
            # If multiple active candidates exist, choose the one with the closest name length to prevent matching Danish India over India
            active_candidates.sort(key=lambda f: abs(len(normalize_name(f.get("properties", {}).get("Name", ""))) - len(norm)))
            return active_candidates[0]
            
        # 2. Fall back to closest snapshot in time from all candidates
        closest_feat = None
        min_dist = float("inf")
        for feat in all_candidate_feats:
            props = feat.get("properties", {})
            from_yr = props.get("FromYear")
            to_yr = props.get("ToYear")
            if from_yr is not None and to_yr is not None:
                dist = min(abs(from_yr - target_year), abs(to_yr - target_year))
                if dist < min_dist:
                    min_dist = dist
                    closest_feat = feat
                    
        return closest_feat

# Singleton instance
cliopatria_db = CliopatriaDatabase()

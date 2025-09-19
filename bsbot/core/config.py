"""Configuration loader with YAML files and environment variable overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import yaml


class Config:
    """Configuration loader with environment variable override support."""

    def __init__(self, config_dir: Optional[str] = None):
        """Initialize config loader.

        Args:
            config_dir: Path to config directory. Defaults to 'config' relative to project root.
        """
        if config_dir is None:
            # Find config directory relative to this file
            current_dir = Path(__file__).parent.parent.parent
            config_dir = current_dir / "config"

        self.config_dir = Path(config_dir)
        self._cache: Dict[str, Any] = {}

    def load_profile(self) -> Dict[str, Any]:
        """Load profile configuration with environment overrides."""
        return self._load_config("profile.yml")

    def load_keys(self) -> Dict[str, Any]:
        """Load key bindings configuration."""
        return self._load_config("keys.yml")

    def load_elements(self, category: str) -> Dict[str, Any]:
        """Load element configurations for a specific category (legacy)."""
        return self._load_config(f"elements/{category}.yml")

    def load_monster_profile(self, monster_id: str) -> Dict[str, Any]:
        """Load a monster profile by id."""
        return self._load_config(f"monsters/{monster_id}.yml")

    def load_interface_profile(self, interface_id: str) -> Dict[str, Any]:
        """Load an interface profile by id."""
        return self._load_config(f"interfaces/{interface_id}.yml")

    def list_monster_profiles(self) -> List[Dict[str, Any]]:
        base = self.config_dir / "monsters"
        if not base.exists():
            return []
        out: List[Dict[str, Any]] = []
        for path in sorted(base.glob("*.yml")):
            data = self.load_monster_profile(path.stem) or {}
            if data:
                out.append({"id": data.get("id") or path.stem, "name": data.get("name")})
            else:
                out.append({"id": path.stem, "name": path.stem})
        return out

    def list_interface_profiles(self) -> List[Dict[str, Any]]:
        base = self.config_dir / "interfaces"
        if not base.exists():
            return []
        out: List[Dict[str, Any]] = []
        for path in sorted(base.glob("*.yml")):
            data = self.load_interface_profile(path.stem) or {}
            out.append({"id": data.get("id") or path.stem, "name": data.get("name")})
        return out

    def _interactable_path(self, interactable_id: str) -> Path:
        return self.config_dir / "interactables" / f"{interactable_id}.yml"

    def load_interactable_profile(self, interactable_id: str) -> Dict[str, Any]:
        """Load an interactable profile by id."""
        return self._load_config(f"interactables/{interactable_id}.yml")

    def list_interactable_profiles(self) -> List[Dict[str, Any]]:
        base = self.config_dir / "interactables"
        if not base.exists():
            return []
        out: List[Dict[str, Any]] = []
        for path in sorted(base.glob("*.yml")):
            data = self.load_interactable_profile(path.stem) or {}
            out.append({"id": data.get("id") or path.stem, "name": data.get("name") or path.stem})
        return out

    def save_interactable_coords(
        self,
        interactable_id: str,
        *,
        coords: Tuple[float, float],
        roi_xy: Optional[Tuple[int, int]] = None,
        screen_xy: Optional[Tuple[int, int]] = None,
        element_index: int = 0,
    ) -> Dict[str, Any]:
        path = self._interactable_path(interactable_id)
        if not path.exists():
            raise FileNotFoundError(f"Interactable profile not found: {interactable_id}")

        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Failed to load interactable profile {interactable_id}: {exc}") from exc

        reference = data.setdefault("reference", {})
        elements = reference.setdefault("elements", [])
        while len(elements) <= element_index:
            elements.append({"label": f"point_{len(elements)}", "kind": "point"})
        element = elements[element_index] or {}
        element["coords"] = [float(coords[0]), float(coords[1])]
        if roi_xy:
            element["roi_xy"] = [int(roi_xy[0]), int(roi_xy[1])]
        if screen_xy:
            element["screen_xy"] = [int(screen_xy[0]), int(screen_xy[1])]
        elements[element_index] = element

        try:
            with path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to save interactable profile {interactable_id}: {exc}") from exc

        cache_key = str(path)
        if cache_key in self._cache:
            self._cache.pop(cache_key, None)
        return data

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load a YAML config file with environment variable overrides."""
        full_path = self.config_dir / config_path

        # Check cache first
        cache_key = str(full_path)
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        config = {}

        # Load YAML file if it exists
        if full_path.exists():
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            except Exception:
                # If YAML loading fails, continue with empty config
                pass

        # Apply environment variable overrides
        config = self._apply_env_overrides(config, config_path)

        # Cache the result
        self._cache[cache_key] = config.copy()

        return config

    def _apply_env_overrides(self, config: Dict[str, Any], config_path: str) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration."""
        # Convert nested dict to flat paths for env var matching
        def flatten_dict(d: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
            flat = {}
            for key, value in d.items():
                new_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    flat.update(flatten_dict(value, new_key))
                else:
                    flat[new_key] = str(value)
            return flat

        # Apply overrides for this config file
        config_name = Path(config_path).stem.upper()
        env_prefix = f"BSBOT_{config_name}_"

        def apply_overrides(obj: Any, path: str = "") -> Any:
            if isinstance(obj, dict):
                result = {}
                for key, value in obj.items():
                    new_path = f"{path}.{key}" if path else key
                    env_key = f"{env_prefix}{new_path.replace('.', '_').upper()}"
                    env_value = os.environ.get(env_key)

                    if env_value is not None:
                        # Try to convert env value to appropriate type
                        if isinstance(value, bool):
                            result[key] = env_value.lower() in ('true', '1', 'yes', 'on')
                        elif isinstance(value, int):
                            try:
                                result[key] = int(env_value)
                            except ValueError:
                                result[key] = value
                        elif isinstance(value, float):
                            try:
                                result[key] = float(env_value)
                            except ValueError:
                                result[key] = value
                        else:
                            result[key] = env_value
                    else:
                        result[key] = apply_overrides(value, new_path)
                return result
            else:
                return obj

        return apply_overrides(config)

    def clear_cache(self):
        """Clear the configuration cache."""
        self._cache.clear()


# Global config instance
_config_instance: Optional[Config] = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


def load_profile() -> Dict[str, Any]:
    """Convenience function to load profile config."""
    return get_config().load_profile()


def load_keys() -> Dict[str, Any]:
    """Convenience function to load key bindings."""
    return get_config().load_keys()


def load_elements(category: str) -> Dict[str, Any]:
    """Convenience function to load element configs."""
    return get_config().load_elements(category)


def load_monster_profile(monster_id: str) -> Dict[str, Any]:
    """Convenience wrapper for monster profiles."""
    return get_config().load_monster_profile(monster_id)


def load_interface_profile(interface_id: str) -> Dict[str, Any]:
    """Convenience wrapper for interface profiles."""
    return get_config().load_interface_profile(interface_id)


def list_monster_profiles() -> List[Dict[str, Any]]:
    """List available monster profiles."""
    return get_config().list_monster_profiles()


def list_interface_profiles() -> List[Dict[str, Any]]:
    """List available interface profiles."""
    return get_config().list_interface_profiles()


def load_interactable_profile(interactable_id: str) -> Dict[str, Any]:
    """Load an interactable profile"""
    return get_config().load_interactable_profile(interactable_id)


def list_interactable_profiles() -> List[Dict[str, Any]]:
    """List available interactable profiles."""
    return get_config().list_interactable_profiles()


def save_interactable_coords(
    interactable_id: str,
    *,
    coords: Tuple[float, float],
    roi_xy: Optional[Tuple[int, int]] = None,
    screen_xy: Optional[Tuple[int, int]] = None,
    element_index: int = 0,
) -> Dict[str, Any]:
    """Persist coordinates into an interactable profile."""
    return get_config().save_interactable_coords(
        interactable_id,
        coords=coords,
        roi_xy=roi_xy,
        screen_xy=screen_xy,
        element_index=element_index,
    )

"""Configuration loader with YAML files and environment variable overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any, Optional
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

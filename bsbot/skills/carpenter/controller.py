from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from bsbot.skills.base import FrameContext, SkillController
from bsbot.core.config import load_interface_profile
from bsbot.vision.detect import (
    configure_tesseract,
    detect_template_multi,
    detect_word_ocr_multi,
)


@dataclass
class WoodType:
    name: str
    requires_lathe: bool = False  # True for Oak, Pine, etc.; False for Ash, Juniper
    xp_per_log: int = 0
    level_requirement: int = 0
    description: str = ""


@dataclass
class StationConfig:
    words: List[str]
    template: Optional[str] = None
    description: str = ""


@dataclass
class CarpenterState:
    current_wood_type: Optional[WoodType] = None
    logs_in_inventory: int = 0
    products_ready: int = 0
    coins_earned: int = 0
    last_action: float = 0.0
    batch_size: int = 12  # Process 12 logs at a time (optimal from wiki)


class CarpenterController(SkillController):
    """Carpenter skill controller for automated wood processing in Brighter Shores."""

    name = "carpenter"

    def __init__(self, runtime):
        super().__init__(runtime)
        self._state = "bank_withdrawal"
        self._carpenter_state = CarpenterState()
        self._last_log_ts = 0.0

        # Load carpenter configuration
        self.interface_profile = load_interface_profile("carpenter") or {}
        self.wood_types = self._load_wood_types()
        self.stations = self._load_stations()
        self.templates = self._load_templates()

        # Processing settings
        self.batch_size = self.interface_profile.get("batch_size", 12)
        self.template_threshold = self.interface_profile.get("template_threshold", 0.8)
        self.ocr_threshold = self.interface_profile.get("ocr_confidence_threshold", 0.7)

        # Update state with config
        self._carpenter_state.batch_size = self.batch_size

    def _load_wood_types(self) -> List[WoodType]:
        """Load wood types from configuration."""
        wood_config = self.interface_profile.get("wood_types", [])
        return [WoodType(**wood) for wood in wood_config] if wood_config else []

    def _load_stations(self) -> Dict[str, StationConfig]:
        """Load station configurations."""
        stations_config = self.interface_profile.get("stations", {})
        stations = {}
        for station_name, config in stations_config.items():
            stations[station_name] = StationConfig(**config)
        return stations

    def _load_templates(self) -> Dict[str, str]:
        """Load template paths from configuration."""
        templates = {}
        ui_templates = self.interface_profile.get("ui_templates", {})
        for name, path in ui_templates.items():
            templates[name] = path

        # Add station templates
        for station_name, station_config in self.stations.items():
            if station_config.template:
                templates[station_name] = station_config.template

        return templates

    def on_start(self, params: Dict[str, object] | None = None) -> None:
        self._state = "bank_withdrawal"
        self._carpenter_state = CarpenterState(batch_size=self.batch_size)
        self._last_log_ts = 0.0

        # Apply any parameters
        if params:
            self._apply_params(params)

        self.runtime.set_state(self._state)
        self.runtime.logger.info("Carpenter skill started - wood processing workflow")

    def on_stop(self) -> None:
        self._state = "bank_withdrawal"
        self.runtime.set_state(self._state)
        self.runtime.logger.info("Carpenter skill stopped")

    def on_update_params(self, params: Dict[str, object] | None = None) -> None:
        if params:
            self._apply_params(params)

    def _apply_params(self, params: Dict[str, object]) -> None:
        """Apply runtime parameters."""
        # Could add parameter handling for specific wood types, etc.
        pass

    def process_frame(self, frame, ctx: FrameContext) -> Tuple[Dict[str, object], Optional[bytes]]:
        status = self.runtime.status
        if status.method in {"auto", "ocr"}:
            configure_tesseract(status.tesseract_path)

        now = time.time()
        result = {}
        annotated = frame.copy()

        # Main carpenter workflow state machine
        if self._state == "bank_withdrawal":
            result = self._withdraw_logs_from_bank(frame)
        elif self._state == "circular_saw":
            result = self._process_at_circular_saw(frame)
        elif self._state == "wood_lathe":
            result = self._process_at_wood_lathe(frame)
        elif self._state == "sell_products":
            result = self._sell_to_timber_merchant(frame)
        elif self._state == "bank_deposit":
            result = self._deposit_coins_to_bank(frame)

        # Add visual annotations
        self._add_visual_annotations(annotated, result)

        # Log state changes
        if now - self._last_log_ts > 2.0:
            wood_name = self._carpenter_state.current_wood_type.name if self._carpenter_state.current_wood_type else "none"
            self.runtime.logger.info(
                f"Carpenter state: {self._state}, wood: {wood_name}, logs: {self._carpenter_state.logs_in_inventory}, products: {self._carpenter_state.products_ready}"
            )
            self._last_log_ts = now

        return result, self._frame_to_jpeg(annotated)

    def _withdraw_logs_from_bank(self, frame) -> Dict[str, object]:
        """Withdraw logs from the Lumber Bank."""
        result = {"state": "bank_withdrawal", "logs_withdrawn": False}

        # Check if bank interface is already open
        bank_open = self._detect_station_interface(frame, "bank")
        if not bank_open.found:
            # Try to open the bank using template or interaction
            bank_opened = self._interact_with_station(frame, "bank")
            if bank_opened:
                result["opening_bank"] = True
                return result

        # Bank is open, withdraw logs
        withdrawal_success = self._perform_log_withdrawal(frame)
        if withdrawal_success:
            self._carpenter_state.logs_in_inventory += self._carpenter_state.batch_size
            result["logs_withdrawn"] = True
            self._select_optimal_wood_type()
            self._transition("circular_saw")

        return result

    def _process_at_circular_saw(self, frame) -> Dict[str, object]:
        """Process logs at the Circular Saw station."""
        result = {"state": "circular_saw", "processing_started": False, "processing_complete": False}

        # Check if saw interface is open
        saw_open = self._detect_station_interface(frame, "circular_saw")
        if not saw_open.found:
            # Navigate to/interact with saw
            saw_opened = self._interact_with_station(frame, "circular_saw")
            if saw_opened:
                result["opening_saw"] = True
                return result

        # Saw is open, check if processing is active
        if not self._detect_active_processing(frame, "saw"):
            # Start processing logs
            processing_started = self._start_processing_at_station(frame, "saw")
            if processing_started:
                result["processing_started"] = True
                self._carpenter_state.last_action = time.time()
                return result

        # Check if processing is complete
        if self._detect_processing_complete(frame, "saw"):
            result["processing_complete"] = True
            self._carpenter_state.products_ready += self._carpenter_state.batch_size

            # Decide next step based on wood type
            if self._carpenter_state.current_wood_type and self._carpenter_state.current_wood_type.requires_lathe:
                self._transition("wood_lathe")
            else:
                self._transition("sell_products")

        return result

    def _process_at_wood_lathe(self, frame) -> Dict[str, object]:
        """Process poles at the Wood Lathe station (for multi-step woods)."""
        result = {"state": "wood_lathe", "processing_started": False, "processing_complete": False}

        # Check if lathe interface is open
        lathe_open = self._detect_station_interface(frame, "wood_lathe")
        if not lathe_open.found:
            # Navigate to/interact with lathe
            lathe_opened = self._interact_with_station(frame, "wood_lathe")
            if lathe_opened:
                result["opening_lathe"] = True
                return result

        # Lathe is open, check if processing is active
        if not self._detect_active_processing(frame, "lathe"):
            # Start processing poles
            processing_started = self._start_processing_at_station(frame, "lathe")
            if processing_started:
                result["processing_started"] = True
                self._carpenter_state.last_action = time.time()
                return result

        # Check if processing is complete
        if self._detect_processing_complete(frame, "lathe"):
            result["processing_complete"] = True
            # Final products ready
            self._transition("sell_products")

        return result

    def _sell_to_timber_merchant(self, frame) -> Dict[str, object]:
        """Sell processed products to the Timber Merchant."""
        result = {"state": "sell_products", "merchant_opened": False, "products_sold": False}

        # Check if merchant interface is open
        merchant_open = self._detect_station_interface(frame, "merchant")
        if not merchant_open.found:
            # Navigate to/interact with merchant
            merchant_opened = self._interact_with_station(frame, "merchant")
            if merchant_opened:
                result["merchant_opened"] = True
                return result

        # Merchant is open, sell products
        sale_success = self._perform_product_sale(frame)
        if sale_success:
            result["products_sold"] = True
            # Track earnings (would need to parse sale confirmation)
            self._carpenter_state.products_ready = 0
            self._transition("bank_deposit")

        return result

    def _deposit_coins_to_bank(self, frame) -> Dict[str, object]:
        """Deposit earned coins back to the bank."""
        result = {"state": "bank_deposit", "bank_opened": False, "coins_deposited": False}

        # Check if bank interface is already open
        bank_open = self._detect_station_interface(frame, "bank")
        if not bank_open.found:
            # Try to open the bank
            bank_opened = self._interact_with_station(frame, "bank")
            if bank_opened:
                result["bank_opened"] = True
                return result

        # Bank is open, deposit coins
        deposit_success = self._perform_coin_deposit(frame)
        if deposit_success:
            result["coins_deposited"] = True
            # Reset for next cycle
            self._carpenter_state.logs_in_inventory = 0
            self._transition("bank_withdrawal")

        return result

    def _detect_station_interface(self, frame, station: str):
        """Detect if a station interface is currently open."""
        from bsbot.vision.detect import Detection

        # Try template detection first
        template_path = self.templates.get(station)
        if template_path:
            try:
                template = cv2.imread(template_path)
                if template is not None:
                    boxes, scores = detect_template_multi(frame, template, threshold=0.8)
                    if boxes:
                        return Detection(True, boxes[0], max(scores))
            except Exception:
                pass

        # Fallback to OCR
        words = self.station_words.get(station, [])
        if words:
            boxes, conf = detect_word_ocr_multi(frame, words)
            if boxes:
                return Detection(True, boxes[0], conf)

        return Detection(False)

    def _interact_with_station(self, frame, station: str) -> bool:
        """Interact with a station to open its interface."""
        # Try "Use Item On" interaction
        use_item_template = self.templates.get("use_item_on")
        if use_item_template:
            try:
                template = cv2.imread(use_item_template)
                if template is not None:
                    boxes, scores = detect_template_multi(frame, template, threshold=0.8)
                    if boxes:
                        x, y, w, h = boxes[0]
                        center_x, center_y = x + w // 2, y + h // 2
                        self.runtime.emit_click([(center_x, center_y, f"use_on_{station}", "click")], f"use_on_{station}")
                        return True
            except Exception:
                pass

        # Fallback: direct interaction with station
        station_detection = self._detect_station_interface(frame, station)
        if station_detection.found:
            x, y, w, h = station_detection.bbox
            center_x, center_y = x + w // 2, y + h // 2
            self.runtime.emit_click([(center_x, center_y, f"interact_{station}", "click")], f"interact_{station}")
            return True

        return False

    def _perform_log_withdrawal(self, frame) -> bool:
        """Perform the log withdrawal action."""
        # Look for withdrawal buttons or amount selectors
        withdrawal_words = ["withdraw", "take", "12"]  # 12 logs at a time
        boxes, conf = detect_word_ocr_multi(frame, withdrawal_words)
        if boxes:
            x, y, w, h = boxes[0]
            center_x, center_y = x + w // 2, y + h // 2
            self.runtime.emit_click([(center_x, center_y, "withdraw_logs", "click")], "withdraw_logs")
            return True
        return False

    def _start_processing_at_station(self, frame, station: str) -> bool:
        """Start processing at the specified station."""
        # Look for start/process buttons
        process_words = ["process", "start", "use", "mill"]
        boxes, conf = detect_word_ocr_multi(frame, process_words)
        if boxes:
            x, y, w, h = boxes[0]
            center_x, center_y = x + w // 2, y + h // 2
            self.runtime.emit_click([(center_x, center_y, f"start_{station}", "click")], f"start_{station}")
            return True
        return False

    def _detect_active_processing(self, frame, station: str) -> bool:
        """Detect if processing is currently active."""
        # Look for progress indicators, animations, or "processing" text
        processing_words = ["processing", "working", "busy"]
        boxes, conf = detect_word_ocr_multi(frame, processing_words)
        return bool(boxes)

    def _detect_processing_complete(self, frame, station: str) -> bool:
        """Detect if processing is complete."""
        # Look for completion indicators
        complete_words = ["complete", "finished", "done", "ready", "collect"]
        boxes, conf = detect_word_ocr_multi(frame, complete_words)
        return bool(boxes)

    def _perform_product_sale(self, frame) -> bool:
        """Perform the product sale action."""
        # Look for sell buttons or trade interface
        trade_template = self.templates.get("trade")
        if trade_template:
            try:
                template = cv2.imread(trade_template)
                if template is not None:
                    boxes, scores = detect_template_multi(frame, template, threshold=0.8)
                    if boxes:
                        x, y, w, h = boxes[0]
                        center_x, center_y = x + w // 2, y + h // 2
                        self.runtime.emit_click([(center_x, center_y, "sell_products", "click")], "sell_products")
                        return True
            except Exception:
                pass

        # Fallback to sell buttons
        sell_words = ["sell", "trade", "merchant"]
        boxes, conf = detect_word_ocr_multi(frame, sell_words)
        if boxes:
            x, y, w, h = boxes[0]
            center_x, center_y = x + w // 2, y + h // 2
            self.runtime.emit_click([(center_x, center_y, "sell_products", "click")], "sell_products")
            return True

        return False

    def _perform_coin_deposit(self, frame) -> bool:
        """Perform the coin deposit action."""
        # Look for deposit buttons in bank interface
        deposit_words = ["deposit", "store", "bank"]
        boxes, conf = detect_word_ocr_multi(frame, deposit_words)
        if boxes:
            x, y, w, h = boxes[0]
            center_x, center_y = x + w // 2, y + h // 2
            self.runtime.emit_click([(center_x, center_y, "deposit_coins", "click")], "deposit_coins")
            return True
        return False

    def _select_optimal_wood_type(self) -> None:
        """Select the best wood type available for processing."""
        # For now, select the first available wood type
        # In future, could optimize based on XP rates and availability
        if self.wood_types:
            self._carpenter_state.current_wood_type = self.wood_types[0]

    def _transition(self, new_state: str) -> None:
        """Transition to a new state."""
        if new_state != self._state:
            self.runtime.logger.info(f"Carpenter transition: {self._state} -> {new_state}")
            self._state = new_state
            self.runtime.set_state(self._state)

    def _add_visual_annotations(self, frame, result: Dict[str, object]) -> None:
        """Add visual annotations to the frame."""
        # Add state information
        cv2.putText(frame, f"Carpenter: {self._state}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # Add wood type info
        if self._carpenter_state.current_wood_type:
            cv2.putText(frame, f"Wood: {self._carpenter_state.current_wood_type.name}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Add inventory info
        cv2.putText(frame, f"Logs: {self._carpenter_state.logs_in_inventory}, Products: {self._carpenter_state.products_ready}", (10, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    def _frame_to_jpeg(self, frame) -> Optional[bytes]:
        """Convert frame to JPEG bytes for preview."""
        try:
            success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if success:
                return buffer.tobytes()
        except Exception:
            pass
        return None
        """Withdraw logs from the Lumber Bank."""
        result = {"state": "bank_withdrawal", "logs_withdrawn": False}

        # Check if bank interface is already open
        bank_open = self._detect_station_interface(frame, "bank")
        if not bank_open.found:
            # Try to open the bank using template or interaction
            bank_opened = self._interact_with_station(frame, "bank")
            if bank_opened:
                result["opening_bank"] = True
                return result

        # Bank is open, withdraw logs
        withdrawal_success = self._perform_log_withdrawal(frame)
        if withdrawal_success:
            self._carpenter_state.logs_in_inventory += self._carpenter_state.batch_size
            result["logs_withdrawn"] = True
            self._select_optimal_wood_type()
            self._transition("circular_saw")

        return result
        """Scan for crafting opportunities and inventory status."""
        result = {"state": "scan", "crafting_available": False, "inventory_full": False}

        # Check for crafting interface already open
        crafting_found = self._detect_crafting_ui(frame)
        if crafting_found.found:
            result["crafting_available"] = True
            self._transition("select_item")
            return result

        # Check inventory status
        inventory_status = self._check_inventory_status(frame)
        if inventory_status.found:
            result["inventory_full"] = True
            self.runtime.logger.info("Inventory full detected")
            return result

        # Look for crafting opportunities (wood piles, etc.)
        crafting_opportunities = self._detect_crafting_opportunities(frame)
        if crafting_opportunities.found:
            result["crafting_available"] = True
            self._transition("open_crafting")
            return result

        return result

    def _open_crafting_interface(self, frame) -> Dict[str, object]:
        """Open the crafting interface."""
        result = {"state": "open_crafting", "interface_opened": False}

        # Look for crafting button or interaction
        if self.crafting_button_template:
            boxes, scores = detect_template_multi(frame, cv2.imread(self.crafting_button_template))
            if boxes:
                # Click the crafting button
                x, y, w, h = boxes[0]
                center_x, center_y = x + w // 2, y + h // 2
                self.runtime.emit_click([(center_x, center_y, "crafting_button", "click")], "crafting_button")
                result["interface_opened"] = True
                self._transition("select_item")
                return result

        # Fallback: OCR for crafting options
        boxes, conf = detect_word_ocr_multi(frame, self.crafting_ui_words)
        if boxes:
            x, y, w, h = boxes[0]
            center_x, center_y = x + w // 2, y + h // 2
            self.runtime.emit_click([(center_x, center_y, "crafting_ui", "click")], "crafting_ui")
            result["interface_opened"] = True
            self._transition("select_item")

        return result

    def _select_crafting_item(self, frame) -> Dict[str, object]:
        """Select an item to craft."""
        result = {"state": "select_item", "item_selected": False}

        # Check if crafting UI is visible
        if not self._detect_crafting_ui(frame).found:
            self._transition("scan")
            return result

        # Try to find and select a crafting item
        for item in self.crafting_items:
            item_found = self._detect_crafting_item(frame, item)
            if item_found.found:
                # Click on the item
                x, y, w, h = item_found.bbox
                center_x, center_y = x + w // 2, y + h // 2
                self.runtime.emit_click([(center_x, center_y, f"craft_{item.name}", "click")], f"craft_{item.name}")
                self._carpenter_state.current_item = item
                result["item_selected"] = True
                result["selected_item"] = item.name
                self._transition("crafting")
                break

        return result

    def _monitor_crafting_progress(self, frame) -> Dict[str, object]:
        """Monitor crafting progress and detect completion."""
        result = {"state": "crafting", "progress": 0.0}  # Placeholder for now

        # Check for crafting completion
        completion_detected = self._detect_crafting_completion(frame)
        if completion_detected.found:
            result["crafting_complete"] = True
            self._transition("collect")
            return result

        # Check for crafting still in progress
        progress = self._detect_crafting_progress(frame)
        # Placeholder - progress tracking not implemented yet
        result["progress"] = progress

        return result

    def _collect_finished_items(self, frame) -> Dict[str, object]:
        """Collect finished crafted items."""
        result = {"state": "collect", "items_collected": False}

        # Look for collect button
        if self.collect_button_template:
            boxes, scores = detect_template_multi(frame, cv2.imread(self.collect_button_template))
            if boxes:
                x, y, w, h = boxes[0]
                center_x, center_y = x + w // 2, y + h // 2
                self.runtime.emit_click([(center_x, center_y, "collect_button", "click")], "collect_button")
                result["items_collected"] = True
                # Item collection not implemented yet
                self._transition("scan")
                return result

        # Fallback: OCR for collect options
        collect_words = ["collect", "take", "claim"]
        boxes, conf = detect_word_ocr_multi(frame, collect_words)
        if boxes:
            x, y, w, h = boxes[0]
            center_x, center_y = x + w // 2, y + h // 2
            self.runtime.emit_click([(center_x, center_y, "collect_items", "click")], "collect_items")
            result["items_collected"] = True
            # Sale completion not implemented yet
            self._transition("scan")

        return result

    def _detect_crafting_ui(self, frame):
        """Detect if crafting UI is open."""
        from bsbot.vision.detect import Detection
        boxes, conf = detect_word_ocr_multi(frame, self.crafting_ui_words)
        return Detection(bool(boxes), boxes[0] if boxes else None, conf)

    def _detect_crafting_opportunities(self, frame):
        """Detect crafting opportunities in the world."""
        from bsbot.vision.detect import Detection
        # Look for wood piles, crafting stations, etc.
        opportunity_words = ["wood", "pile", "craft", "station"]
        boxes, conf = detect_word_ocr_multi(frame, opportunity_words)
        return Detection(bool(boxes), boxes[0] if boxes else None, conf)

    def _detect_crafting_item(self, frame, item: CraftingItem):
        """Detect a specific crafting item."""
        from bsbot.vision.detect import Detection

        # Try template first
        if item.template_path:
            try:
                template = cv2.imread(item.template_path)
                if template is not None:
                    boxes, scores = detect_template_multi(frame, template)
                    if boxes:
                        return Detection(True, boxes[0], max(scores))
            except Exception:
                pass

        # Fall back to OCR
        if item.ocr_words:
            boxes, conf = detect_word_ocr_multi(frame, item.ocr_words)
            if boxes:
                return Detection(True, boxes[0], conf)

        return Detection(False)

    def _check_inventory_status(self, frame):
        """Check if inventory is full."""
        from bsbot.vision.detect import Detection
        boxes, conf = detect_word_ocr_multi(frame, self.inventory_full_words)
        return Detection(bool(boxes), confidence=conf)

    def _detect_crafting_progress(self, frame) -> float:
        """Detect crafting progress (0.0 to 1.0)."""
        # Look for progress bars, timers, etc.
        progress_words = ["progress", "crafting", "remaining"]
        boxes, conf = detect_word_ocr_multi(frame, progress_words)
        return min(conf, 1.0)  # Rough approximation

    def _detect_crafting_completion(self, frame):
        """Detect if crafting is complete."""
        from bsbot.vision.detect import Detection
        completion_words = ["complete", "finished", "done", "collect"]
        boxes, conf = detect_word_ocr_multi(frame, completion_words)
        return Detection(bool(boxes), boxes[0] if boxes else None, conf)

    def _transition(self, new_state: str) -> None:
        """Transition to a new state."""
        if new_state != self._state:
            self.runtime.logger.info(f"Carpenter transition: {self._state} -> {new_state}")
            self._state = new_state
            self.runtime.set_state(self._state)

    def _add_visual_annotations(self, frame, result: Dict[str, object]) -> None:
        """Add visual annotations to the frame."""
        # Add state information
        cv2.putText(frame, f"Carpenter: {self._state}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # Add current item info
        # Item display not implemented yet

    def _frame_to_jpeg(self, frame) -> Optional[bytes]:
        """Convert frame to JPEG bytes for preview."""
        try:
            success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if success:
                return buffer.tobytes()
        except Exception:
            pass
        return None

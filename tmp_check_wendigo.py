import cv2
from bsbot.vision.detect import detect_template_multi
shot = cv2.imread('assets/screenshots/screenshot_without_minimap_wendigo_attackButton.png')
tpl = cv2.imread('assets/templates/wendigo2.png')
boxes, scores = detect_template_multi(shot, tpl)
print('boxes', boxes)
print('scores', scores)

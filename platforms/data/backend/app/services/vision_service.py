import os
import base64
import csv

# Robust Import Handling
try:
    import cv2
    import numpy as np
    from ultralytics import YOLO
    _deps_ok = True
    _deps_error = None
except ImportError as e:
    _deps_ok = False
    _deps_error = str(e)
    print(f"Vision Service Warning: Dependencies missing ({e}). Vision features will be unavailable.")


class VisionService:
    def __init__(self):
        self.models = {}
        self.model_load_errors = {}
        self.task_labels = {
            "wetting": "润湿",
            "solderball": "锡珠",
            "collapse": "坍塌",
        }

        try:
            backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            runs_root = os.path.join(backend_root, "models", "yolo")
            self.model_paths = {
                "wetting": os.path.join(runs_root, "wetting_all_cls", "weights", "best.pt"),
                "solderball": os.path.join(runs_root, "solderball_all_cls", "weights", "best.pt"),
                "collapse": os.path.join(runs_root, "collapse_all_cls", "weights", "best.pt"),
            }
        except Exception as e:
            print(f"Error calculating paths: {e}")
            self.model_paths = {}

        if _deps_ok:
            for task in list(self.model_paths.keys()):
                self.load_model(task)

    def load_model(self, task):
        if not _deps_ok:
            return

        model_path = self.model_paths.get(task)
        if model_path and os.path.exists(model_path):
            try:
                self.models[task] = YOLO(model_path)
                print(f"YOLOv11 model loaded for {task} from {model_path}")
            except Exception as e:
                print(f"Failed to load YOLOv11 model for {task}: {e}")
                self.model_load_errors[task] = str(e)
        else:
            self.model_load_errors[task] = "File not found"
            print(f"Model file not found for {task}: {model_path}")

    def predict(self, image_bytes, task="wetting"):
        if not _deps_ok:
            return {"error": f"后端缺失依赖: {_deps_error}. 请在服务器执行: `pip install ultralytics opencv-python`"}

        task = str(task or "wetting").strip().lower()
        if task not in self.model_paths:
            return {"error": f"不支持的图片分类任务: {task}"}

        if task not in self.models:
            self.load_model(task)
            if task not in self.models:
                return {
                    "error": f"{self.task_labels.get(task, task)}模型加载失败 "
                    f"(Path: {self.model_paths.get(task)}). 请检查主模型是否存在。"
                }

        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return {"error": "Failed to decode image"}

            results = self.models[task](img)
            predictions = []
            if results:
                result = results[0]
                if hasattr(result, "probs") and result.probs is not None:
                    top5 = result.probs.top5
                    top5conf = result.probs.top5conf
                    if top5 and top5conf is not None:
                        for i in range(len(top5)):
                            conf = float(top5conf[i])
                            if conf > 0.01:
                                predictions.append({
                                    "class": result.names[top5[i]],
                                    "confidence": conf,
                                    "bbox": []
                                })

                annotated_frame = result.plot()
                _, buffer = cv2.imencode(".jpg", annotated_frame)
                img_base64 = base64.b64encode(buffer).decode("utf-8")
                return {
                    "task": task,
                    "task_label": self.task_labels.get(task, task),
                    "predictions": predictions,
                    "image_base64": f"data:image/jpeg;base64,{img_base64}",
                    "count": len(predictions),
                    "model_path": self.model_paths.get(task),
                }
            return {"task": task, "predictions": [], "image_base64": None, "count": 0}

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Inference Error: {str(e)}"}

    def predict_from_path(self, image_path, task="wetting"):
        """
        Predict from image file path on disk.
        Returns: {"class": "等级名", "confidence": 0.95} or {"error": "..."}
        """
        if not _deps_ok:
            return {"error": f"后端缺失依赖: {_deps_error}"}

        task = str(task or "wetting").strip().lower()
        if task not in self.model_paths:
            return {"error": f"不支持的图片分类任务: {task}"}

        if not os.path.exists(image_path):
            return {"error": f"图片文件不存在: {image_path}"}

        if task not in self.models:
            self.load_model(task)
            if task not in self.models:
                return {"error": f"{self.task_labels.get(task, task)}模型加载失败"}

        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"error": f"无法读取图片: {image_path}"}

            results = self.models[task](img)
            if results:
                result = results[0]
                if hasattr(result, "probs") and result.probs is not None:
                    top1_idx = result.probs.top1
                    top1_conf = float(result.probs.top1conf) if result.probs.top1conf is not None else 0.0
                    class_name = result.names[top1_idx]
                    return {
                        "class": class_name,
                        "confidence": top1_conf,
                        "task": task,
                        "task_label": self.task_labels.get(task, task),
                    }
            return {"error": "未检测到分类结果"}

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Inference Error: {str(e)}"}

    def get_model_infos(self):
        items = []
        for task, model_path in self.model_paths.items():
            run_dir = os.path.dirname(os.path.dirname(model_path))
            results_csv = os.path.join(run_dir, "results.csv")
            metrics = {}
            if os.path.exists(results_csv):
                try:
                    with open(results_csv, "r", encoding="utf-8") as f:
                        rows = list(csv.DictReader(f))
                    if rows:
                        last = rows[-1]
                        metrics = {
                            "epoch": int(float(last.get("epoch", 0) or 0)),
                            "top1": float(last.get("metrics/accuracy_top1", 0) or 0),
                            "top5": float(last.get("metrics/accuracy_top5", 0) or 0),
                            "val_loss": float(last.get("val/loss", 0) or 0),
                            "train_loss": float(last.get("train/loss", 0) or 0),
                        }
                except Exception as exc:
                    metrics = {"error": str(exc)}
            items.append({
                "task": task,
                "task_label": self.task_labels.get(task, task),
                "model_path": model_path,
                "is_loaded": task in self.models,
                "exists": os.path.exists(model_path),
                "load_error": self.model_load_errors.get(task),
                "metrics": metrics,
            })
        return items


vision_service = VisionService()

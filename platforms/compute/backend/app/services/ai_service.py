import json
import math
import os
import re
import time
import warnings
from copy import deepcopy

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

warnings.filterwarnings("ignore")

PARTICLE_JSON_COL = "粒度分布_实测值_JSON"
TRACE_COLS_FOR_SN = ["Pb", "Ag", "Fe", "Cu", "Bi", "Sb", "As", "Zn", "Al", "Cd", "Ni"]


class SolderTextAI:
    """新版正向文本模型：配方/成分/粒度分布 -> 六目标输出。"""

    def __init__(self):
        self.categorical_features = ["助焊膏"]
        self.base_numeric_features = [
            "助焊剂比例%",
            "合金含量（%）",
            "助焊剂比例_归一化",
            "合金含量_归一化",
            "Ag",
            "Cu",
            "Pb_numeric",
            "Fe",
            "Bi",
            "Sb",
            "氧含量_实测值",
            "Sn_numeric",
        ]
        self.particle_feature_map = {}
        self.numeric_features = list(self.base_numeric_features)
        self.feature_columns = self.categorical_features + self.numeric_features
        self.target_configs = {
            "黏度初值": {
                "task": "regression",
                "model": ExtraTreesRegressor(
                    n_estimators=400, random_state=42, min_samples_leaf=2, n_jobs=-1
                ),
            },
            "Ti": {
                "task": "regression",
                "model": ExtraTreesRegressor(
                    n_estimators=400, random_state=42, min_samples_leaf=2, n_jobs=-1
                ),
            },
            "锡粉规格": {
                "task": "classification",
                "model": ExtraTreesClassifier(
                    n_estimators=500,
                    random_state=42,
                    min_samples_leaf=2,
                    class_weight="balanced_subsample",
                    n_jobs=-1,
                ),
            },
            "润湿等级": {
                "task": "classification",
                "model": ExtraTreesClassifier(
                    n_estimators=500,
                    random_state=42,
                    min_samples_leaf=2,
                    class_weight="balanced_subsample",
                    n_jobs=-1,
                ),
            },
            "坍塌类别": {
                "task": "classification",
                "model": ExtraTreesClassifier(
                    n_estimators=500,
                    random_state=42,
                    min_samples_leaf=2,
                    class_weight="balanced_subsample",
                    n_jobs=-1,
                ),
            },
            "锡珠等级": {
                "task": "classification",
                "model": ExtraTreesClassifier(
                    n_estimators=500,
                    random_state=42,
                    min_samples_leaf=2,
                    class_weight="balanced_subsample",
                    n_jobs=-1,
                ),
            },
        }
        self.models = {}
        self.metrics = {}
        self.training_rows = 0

        # === 黏度对助焊剂比例的物理修正层（领域知识先验，软规则） ===
        # 背景：训练数据里 11~12% 区间助焊剂比例与黏度呈弱相关（存在混杂），
        # 模型对该强单调物理效应欠拟合，导致单点预测/影响分析里黏度随比例变化太小，
        # 不符合实际产线经验。此处注入软规则：参考点附近每 +0.1 比例，黏度约降 8 Pa·s；
        # 远离参考点时用 tanh 饱和，避免硬折线/完全线性带来的"刻意感"，同时保持局部斜率。
        # 修正写在方法内，重新训练后依然生效，且单点预测与影响分析一致。
        self.viscosity_correction_enabled = True
        self.viscosity_correction_ref_flux_norm = 11.5   # 参考归一化助焊剂比例 (%)
        self.viscosity_correction_slope = -8.0           # 参考点处局部斜率 (Pa·s / 每 0.1 比例)
        self.viscosity_correction_unit = 0.1             # 比例步长
        self.viscosity_correction_saturation = 100.0     # 修正饱和幅度 (Pa·s)，越大"硬规则"作用范围越远
        self.viscosity_correction_min = 50.0             # 下限 clamp (Pa·s)
        self.viscosity_correction_max = 300.0            # 上限 clamp (Pa·s)

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.model_path = os.path.join(project_root, "solder_model_v4.pkl")
        self.metrics_path = os.path.join(project_root, "solder_model_v4_metrics.json")
        self.model_info = {
            "name": "SolderAI_Text_v4",
            "status": "未训练",
            "last_trained": None,
            "accuracy": {
                "spec_acc": 0.0,
                "wetting_acc": 0.0,
                "collapse_acc": 0.0,
                "solderball_acc": 0.0,
                "viscosity_r2": 0.0,
                "ti_r2": 0.0,
            },
            "metrics": {},
            "training_rows": 0,
            "feature_count": 0,
            "particle_feature_count": 0,
            "particle_feature_labels": [],
        }

        if os.path.exists(self.model_path):
            try:
                self.load_model(self.model_path)
                self.model_info["status"] = "已加载"
                self.model_info["last_trained"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(self.model_path))
                )
                self._refresh_model_info()
            except Exception as exc:
                print(f"自动加载模型失败: {exc}")

    def _rebuild_feature_columns(self) -> None:
        self.numeric_features = self.base_numeric_features + list(self.particle_feature_map.values())
        self.feature_columns = self.categorical_features + self.numeric_features

    def _refresh_model_info(self) -> None:
        self.model_info["name"] = "SolderAI_Text_v4"
        self.model_info["accuracy"] = {
            "spec_acc": round(float(self.metrics.get("锡粉规格", {}).get("accuracy", 0.0)), 4),
            "wetting_acc": round(float(self.metrics.get("润湿等级", {}).get("accuracy", 0.0)), 4),
            "collapse_acc": round(float(self.metrics.get("坍塌类别", {}).get("accuracy", 0.0)), 4),
            "solderball_acc": round(float(self.metrics.get("锡珠等级", {}).get("accuracy", 0.0)), 4),
            "viscosity_r2": round(float(self.metrics.get("黏度初值", {}).get("r2", 0.0)), 4),
            "ti_r2": round(float(self.metrics.get("Ti", {}).get("r2", 0.0)), 4),
        }
        self.model_info["metrics"] = deepcopy(self.metrics)
        self.model_info["training_rows"] = int(self.training_rows or 0)
        self.model_info["feature_count"] = len(self.feature_columns)
        self.model_info["particle_feature_count"] = len(self.particle_feature_map)
        self.model_info["particle_feature_labels"] = list(self.particle_feature_map.keys())

    @staticmethod
    def _safe_float(value, default=0.0) -> float:
        if pd.isna(value):
            return default
        text = str(value).strip()
        if not text:
            return default
        text = text.replace("＜", "").replace("<", "").replace(">", "").replace("＞", "")
        try:
            return float(text)
        except ValueError:
            return default

    @staticmethod
    def _normalize_particle_key(raw_key: str) -> str:
        text = str(raw_key).strip()
        text = text.replace("μ", "u").replace("µ", "u")
        text = text.replace("～", "_to_")
        text = text.replace("<", "lt_")
        text = text.replace(">", "gt_")
        text = re.sub(r"[^0-9A-Za-z_]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return f"粒度分布_{text}" if text else "粒度分布_unknown"

    def _discover_particle_feature_map(self, series: pd.Series) -> None:
        discovered_keys = set(self.particle_feature_map.keys())
        for value in series.dropna().astype(str):
            raw_text = value.strip()
            if not raw_text:
                continue
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                continue
            for raw_key in data.keys():
                discovered_keys.add(str(raw_key))
        self.particle_feature_map = {
            raw_key: self._normalize_particle_key(raw_key) for raw_key in sorted(discovered_keys)
        }
        self._rebuild_feature_columns()

    def _parse_particle_distribution(self, value) -> dict:
        parsed = {feature_name: 0.0 for feature_name in self.particle_feature_map.values()}
        if pd.isna(value):
            return parsed
        raw_text = str(value).strip()
        if not raw_text:
            return parsed
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            return parsed
        for raw_key, raw_value in data.items():
            feature_name = self.particle_feature_map.get(str(raw_key))
            if feature_name:
                parsed[feature_name] = self._safe_float(raw_value, 0.0)
        return parsed

    def _estimate_pb_value(self, row: pd.Series) -> float:
        pb_raw = row.get("Pb_raw", row.get("Pb"))
        pb_numeric = self._safe_float(pb_raw, default=np.nan)
        if not np.isnan(pb_numeric):
            return pb_numeric
        if "余量" in str(pb_raw):
            remainder = 100.0 - self._safe_float(row.get("Sn_raw", row.get("Sn")), default=0.0)
            for col in TRACE_COLS_FOR_SN:
                if col == "Pb":
                    continue
                remainder -= self._safe_float(row.get(col), default=0.0)
            return max(remainder, 0.0)
        return 0.0

    def _estimate_sn_value(self, row: pd.Series) -> float:
        sn_raw = row.get("Sn_raw", row.get("Sn"))
        sn_numeric = self._safe_float(sn_raw, default=np.nan)
        if not np.isnan(sn_numeric):
            return sn_numeric
        remainder = 100.0 - self._estimate_pb_value(row)
        for col in ["Ag", "Fe", "Cu", "Bi", "Sb", "As", "Zn", "Al", "Cd", "Ni"]:
            remainder -= self._safe_float(row.get(col), default=0.0)
        return max(remainder, 0.0)

    def preprocess(self, df: pd.DataFrame, update_particle_features: bool = True) -> pd.DataFrame:
        data = df.copy()
        required_inputs = ["助焊膏", "助焊剂比例%", "合金含量（%）", PARTICLE_JSON_COL]
        required_targets = list(self.target_configs.keys())
        for col in required_inputs + required_targets:
            if col not in data.columns:
                data[col] = np.nan
        data = data.dropna(subset=required_inputs + required_targets)
        if data.empty:
            return data

        data["Pb_raw"] = data["Pb"] if "Pb" in data.columns else np.nan
        data["Sn_raw"] = data["Sn"] if "Sn" in data.columns else np.nan

        numeric_cols = [
            "助焊剂比例%",
            "合金含量（%）",
            "Ag",
            "Cu",
            "Pb",
            "Fe",
            "Bi",
            "Sb",
            "氧含量_实测值",
            "黏度初值",
            "Ti",
            "润湿等级",
            "锡珠等级",
            *TRACE_COLS_FOR_SN,
        ]
        for col in numeric_cols:
            if col not in data.columns:
                data[col] = 0.0
            data[col] = data[col].apply(lambda value: self._safe_float(value, default=np.nan))

        data["助焊膏"] = data["助焊膏"].astype(str).str.strip()
        data["锡粉规格"] = data["锡粉规格"].astype(str).str.strip()
        data["坍塌类别"] = data["坍塌类别"].astype(str).str.strip()

        if update_particle_features or not self.particle_feature_map:
            self._discover_particle_feature_map(data[PARTICLE_JSON_COL])

        particle_df = pd.DataFrame(
            [self._parse_particle_distribution(value) for value in data[PARTICLE_JSON_COL]],
            index=data.index,
        )
        data = pd.concat([data, particle_df], axis=1)

        total = data["助焊剂比例%"] + data["合金含量（%）"]
        total = total.replace(0, np.nan)
        data["助焊剂比例_归一化"] = (data["助焊剂比例%"] / total) * 100
        data["合金含量_归一化"] = (data["合金含量（%）"] / total) * 100
        data["Pb_numeric"] = data.apply(self._estimate_pb_value, axis=1)
        data["Sn_numeric"] = data.apply(self._estimate_sn_value, axis=1)

        data = data.dropna(
            subset=self.feature_columns + ["黏度初值", "Ti", "锡粉规格", "润湿等级", "坍塌类别", "锡珠等级"]
        )
        if data.empty:
            return data
        data["润湿等级"] = data["润湿等级"].astype(int).astype(str)
        data["锡珠等级"] = data["锡珠等级"].astype(int).astype(str)
        data["坍塌类别"] = data["坍塌类别"].replace({"cold": "冷", "hot": "热"}).astype(str)
        data = data.reset_index(drop=True)
        return data

    def _build_pipeline(self, estimator):
        transformer = ColumnTransformer(
            transformers=[
                ("cat", OneHotEncoder(handle_unknown="ignore"), self.categorical_features),
                ("num", "passthrough", self.numeric_features),
            ]
        )
        return Pipeline(steps=[("transform", transformer), ("model", clone(estimator))])

    def evaluate(self, data: pd.DataFrame, test_size: float = 0.2, random_state: int = 42) -> dict:
        X = data[self.feature_columns]
        train_idx, test_idx = train_test_split(
            np.arange(len(data)), test_size=test_size, random_state=random_state
        )
        metrics = {}
        for target_name, config in self.target_configs.items():
            pipeline = self._build_pipeline(config["model"])
            y_train = data.iloc[train_idx][target_name]
            y_test = data.iloc[test_idx][target_name]
            pipeline.fit(X.iloc[train_idx], y_train)
            y_pred = pipeline.predict(X.iloc[test_idx])
            if config["task"] == "regression":
                metrics[target_name] = {
                    "task": "regression",
                    "r2": round(float(r2_score(y_test, y_pred)), 6),
                    "mae": round(float(mean_absolute_error(y_test, y_pred)), 6),
                }
            else:
                metrics[target_name] = {
                    "task": "classification",
                    "accuracy": round(float(accuracy_score(y_test, y_pred)), 6),
                    "label_distribution": data[target_name].astype(str).value_counts().to_dict(),
                }
        return metrics

    def fit(self, data: pd.DataFrame) -> None:
        X = data[self.feature_columns]
        self.models = {}
        for target_name, config in self.target_configs.items():
            pipeline = self._build_pipeline(config["model"])
            pipeline.fit(X, data[target_name])
            self.models[target_name] = pipeline
        self.training_rows = len(data)

    def train(self, df_raw: pd.DataFrame):
        print("正在进行预处理...")
        data = self.preprocess(df_raw, update_particle_features=True)
        if data.empty:
            return False, "预处理后没有可用训练数据。"
        self.metrics = self.evaluate(data)
        self.fit(data)
        self.save_model(self.model_path)
        self.save_metrics(self.metrics_path)
        self.model_info["status"] = "训练完成"
        self.model_info["last_trained"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._refresh_model_info()
        return True, f"训练成功，可用样本 {len(data)} 条"

    def _classification_top_probs(self, pipeline: Pipeline, X: pd.DataFrame) -> list:
        model = pipeline.named_steps["model"]
        probs = pipeline.predict_proba(X)[0]
        labels = [str(label) for label in model.classes_]
        return sorted(
            [{"label": label, "prob": float(prob)} for label, prob in zip(labels, probs)],
            key=lambda item: item["prob"],
            reverse=True,
        )[:3]

    def _reference_viscosity(self, feature_dict: dict):
        """在参考归一化助焊剂比例处、保持其他配方不变，求模型对黏度的预测值（锚点）。

        保持配方总量(flux+alloy)不变，仅把助焊剂/合金比例调整为参考归一化比例，
        这样锚点只反映"其他特征在参考比例下的黏度"，后续用线性硬规则叠加比例效应。
        """
        try:
            flux = float(feature_dict.get("助焊剂比例%"))
            alloy = float(feature_dict.get("合金含量（%）"))
        except (TypeError, ValueError):
            return None
        if (flux + alloy) <= 0:
            return None
        total = flux + alloy
        ref = self.viscosity_correction_ref_flux_norm
        new_flux = ref / 100.0 * total
        new_alloy = total - new_flux
        ref_row = deepcopy(feature_dict)
        ref_row["助焊剂比例%"] = new_flux
        ref_row["合金含量（%）"] = new_alloy
        ref_one_row = {
            **ref_row,
            "黏度初值": 0.0,
            "Ti": 0.0,
            "锡粉规格": "4A",
            "润湿等级": 1,
            "坍塌类别": "冷",
            "锡珠等级": 1,
        }
        frame = self.preprocess(pd.DataFrame([ref_one_row]), update_particle_features=False)
        if frame.empty or "黏度初值" not in self.models:
            return None
        X_ref = frame[self.feature_columns]
        try:
            return float(self.models["黏度初值"].predict(X_ref)[0])
        except Exception:
            return None

    def _apply_viscosity_correction(self, raw_visc: float, anchored_visc, feature_dict: dict) -> float:
        """用锚点 + tanh 软饱和规则修正黏度，并 clamp 到合理区间。

        核心：参考点处局部斜率精确等于 slope；远离参考点时修正量通过 tanh 平滑饱和，
        避免"完全线性/折线"带来的刻意感，同时保留强单调趋势。
        """
        if anchored_visc is None:
            return raw_visc
        try:
            flux = float(feature_dict.get("助焊剂比例%"))
            alloy = float(feature_dict.get("合金含量（%）"))
        except (TypeError, ValueError):
            return raw_visc
        if (flux + alloy) <= 0:
            return raw_visc
        flux_norm = flux / (flux + alloy) * 100.0
        step = (flux_norm - self.viscosity_correction_ref_flux_norm) / self.viscosity_correction_unit

        # 线性硬规则目标值
        target = float(anchored_visc) + self.viscosity_correction_slope * step
        deviation = target - float(raw_visc)

        # tanh 软饱和：在参考点附近 ≈ 线性（斜率≈slope），远离后渐近饱和
        saturation = self.viscosity_correction_saturation
        corrected = float(raw_visc) + saturation * math.tanh(deviation / saturation)
        corrected = max(self.viscosity_correction_min, min(self.viscosity_correction_max, corrected))
        return corrected

    def predict_forward(self, feature_dict: dict) -> dict:
        if not self.models:
            raise RuntimeError("模型尚未训练或加载。")

        row = deepcopy(feature_dict)
        row.setdefault(PARTICLE_JSON_COL, "{}")
        one_row = {
            **row,
            "黏度初值": 0.0,
            "Ti": 0.0,
            "锡粉规格": "4A",
            "润湿等级": 1,
            "坍塌类别": "冷",
            "锡珠等级": 1,
        }
        frame = self.preprocess(pd.DataFrame([one_row]), update_particle_features=False)
        if frame.empty:
            raise RuntimeError("输入特征无法通过预处理，请检查数值范围与粒度分布 JSON。")
        X = frame[self.feature_columns]

        result = {}
        anchored_visc = None
        if self.viscosity_correction_enabled:
            anchored_visc = self._reference_viscosity(row)
        for target_name, pipeline in self.models.items():
            pred = pipeline.predict(X)[0]
            if target_name in ("黏度初值", "Ti"):
                val = float(pred)
                if target_name == "黏度初值" and anchored_visc is not None:
                    val = self._apply_viscosity_correction(val, anchored_visc, row)
                result[target_name] = round(val, 6)
            else:
                result[target_name] = str(pred)
                result[f"{target_name}_top_probs"] = self._classification_top_probs(pipeline, X)
        return result

    def save_model(self, filepath: str = None) -> None:
        filepath = filepath or self.model_path
        joblib.dump(self, filepath)
        print(f"模型已保存至: {filepath}")

    def save_metrics(self, filepath: str = None) -> None:
        filepath = filepath or self.metrics_path
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "training_rows": self.training_rows,
                    "feature_columns": self.feature_columns,
                    "particle_feature_map": self.particle_feature_map,
                    "metrics": self.metrics,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def load_model(self, filepath: str = None):
        filepath = filepath or self.model_path
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"找不到模型文件: {filepath}")
        try:
            loaded_obj = joblib.load(filepath)
        except Exception as e:
            print(f"直接加载失败，尝试使用替代方式: {e}")
            loaded_obj = joblib.load(filepath, mmap_mode=None)
        self.__dict__.update(loaded_obj.__dict__)
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.model_path = os.path.join(_root, "solder_model_v4.pkl")
        self.metrics_path = os.path.join(_root, "solder_model_v4_metrics.json")
        self._refresh_model_info()
        return self


ai_engine = SolderTextAI()

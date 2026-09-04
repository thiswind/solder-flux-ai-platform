from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.app.core.database import Base

class Experiment(Base):
    """
    实验记录表
    存储每一次锡膏配方实验的输入(X)和结果(Y)
    """
    __tablename__ = "experiments"

    # 主键 ID，自增
    id = Column(Integer, primary_key=True, index=True)
    
    # 实验名称
    experiment_name = Column(String, index=True)
    
    # 关键：配方数据 (X) - 使用 JSON 格式存储，方便未来扩展
    # 例如: {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}
    composition_x = Column(JSON, nullable=False)
    
    # 关键：实验结果 (Y) - 使用 JSON 格式存储
    # 例如: {"viscosity": 180.5, "melting_point": 217}
    properties_y = Column(JSON, nullable=True)
    
    # 创建时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DataUpload(Base):
    """
    数据上传记录表
    """
    __tablename__ = "data_uploads"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    description = Column(String, nullable=True)
    row_count = Column(Integer, default=0)
    # 去重指纹：L1 文件字节哈希（sha256），L2 解析后内容哈希（sha256）
    file_hash = Column(String(64), nullable=True, index=True)
    content_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    data_items = relationship("SolderPasteData", back_populates="upload", cascade="all, delete-orphan")

class SolderPasteData(Base):
    """
    锡膏数据表（适配新版 processed_data.xlsx）
    """
    __tablename__ = "solder_paste_data"

    id = Column(Integer, primary_key=True, index=True)
    
    upload_id = Column(Integer, ForeignKey("data_uploads.id"), nullable=True)
    upload = relationship("DataUpload", back_populates="data_items")
    
    # 标识与基础配方
    serial_number = Column(Integer, nullable=True)
    product_batch = Column(String, index=True, nullable=True)
    product_model = Column(String, index=True, nullable=True)
    flux_paste = Column(String, index=True, nullable=True)
    flux_percent = Column(Float, nullable=True)
    alloy_content = Column(Float, nullable=True)
    alloy_grade = Column(String, index=True, nullable=True)
    powder_batch = Column(String, nullable=True)
    sn = Column(String, nullable=True)
    pb = Column(Float, nullable=True)
    as_ = Column(Float, nullable=True)
    ag = Column(Float, nullable=True)
    fe = Column(Float, nullable=True)
    cu = Column(Float, nullable=True)
    bi = Column(Float, nullable=True)
    sb = Column(Float, nullable=True)
    zn = Column(Float, nullable=True)
    al = Column(Float, nullable=True)
    cd = Column(Float, nullable=True)
    ni = Column(Float, nullable=True)

    # 粒度分布与工艺参数
    particle_distribution_std_json = Column(JSON, nullable=True)
    particle_distribution_real_json = Column(JSON, nullable=True)
    oxygen_std = Column(String, nullable=True)
    oxygen_real = Column(Float, nullable=True)
    sphericity_std = Column(String, nullable=True)
    sphericity_real = Column(String, nullable=True)
    powder_spec = Column(String, index=True, nullable=True)
    powder_oxygen = Column(String, nullable=True)
    viscosity_initial = Column(Float, nullable=True)
    ti_index = Column(Float, nullable=True)
    viscosity_device_id = Column(String, nullable=True)
    inspector = Column(String, nullable=True)

    # 图片路径
    wetting_image_path = Column(String, nullable=True)
    solderball_image_path = Column(String, nullable=True)
    collapse_image_path = Column(String, nullable=True)
    stability_image_path = Column(String, nullable=True)
    original_wetting_image_path = Column(String, nullable=True)
    wetting_more_details = Column(Text, nullable=True)
    original_solderball_image_path = Column(String, nullable=True)
    solderball_more_details = Column(Text, nullable=True)
    original_collapse_image_path = Column(String, nullable=True)
    collapse_more_details = Column(Text, nullable=True)
    original_stability_image_path = Column(String, nullable=True)
    stability_more_details = Column(Text, nullable=True)

    # 图像标签与来源
    wetting_level = Column(String, index=True, nullable=True)
    wetting_level_source = Column(String, nullable=True)
    wetting_level_confidence = Column(Float, nullable=True)
    solderball_level = Column(String, index=True, nullable=True)
    solderball_level_source = Column(String, nullable=True)
    solderball_level_confidence = Column(Float, nullable=True)
    collapse_category = Column(String, index=True, nullable=True)
    collapse_category_source = Column(String, nullable=True)
    collapse_category_confidence = Column(Float, nullable=True)

    # 数据来源
    overall_source = Column(String, nullable=True)
    production_batch = Column(String, nullable=True)
    specific_source = Column(String, nullable=True)
    raw_payload = Column(JSON, nullable=True)

    # 行级去重指纹：基于 raw_payload 规范化计算的 sha256，用于跨上传/库内行级去重
    row_hash = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

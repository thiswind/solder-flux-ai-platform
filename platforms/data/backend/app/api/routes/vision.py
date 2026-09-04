from fastapi import APIRouter, File, Form, UploadFile

from app.services.vision_service import vision_service

router = APIRouter(prefix="/vision", tags=["vision"])


@router.post("/detect")
async def detect_image(file: UploadFile = File(...), task: str = Form(...)):
    """对单张图片进行 YOLO 分类预测。"""
    image_bytes = await file.read()
    result = vision_service.predict(image_bytes, task)
    return result


@router.get("/models")
async def get_models():
    """获取所有视觉模型的状态信息。"""
    return {"items": vision_service.get_model_infos()}
from fastapi import APIRouter, Depends, status, HTTPException
from typing import Annotated
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.db import engine
from app.backend.db_depends import get_db
from sqlalchemy import select, insert, update, and_

from app.routers.auth import get_current_user
from app.schemas import CreateProduct
from app.models import *

router = APIRouter(prefix='/products', tags=['products'])


@router.get('/')
async def all_products(db: Annotated[AsyncSession, Depends(get_db)]):
    # Метод получения всех активных товаров
    products = await db.scalars(select(Product).where(Product.is_active == True, Product.stock > 0))
    if not products.all():
        raise HTTPException(  # Вызываем исключение вместо возврата
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Товары не найдены'
        )
    return products.all()


@router.post('/create')
async def create_product(
        db: Annotated[AsyncSession, Depends(get_db)],
        create_product: CreateProduct,
        get_user: Annotated[dict, Depends(get_current_user)]
):
    # Метод создания товара с проверкой прав
    if get_user.get('is_supplier') or get_user.get('is_admin'):
        slug = slugify(create_product.name)
        existing_product = await db.scalar(select(Product).where(Product.slug == slug))
        if existing_product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Товар с таким названием уже существует'
            )
        await db.execute(insert(Product).values(
            name=create_product.name,
            description=create_product.description,
            price=create_product.price,
            image_url=create_product.image_url,
            stock=create_product.stock,
            category_id=create_product.category_id,  # Исправлено имя поля
            rating=0.0,
            slug=slug,
            supplier_id=get_user.get('id')))
        await db.commit()
        return {'status_code': 201, 'transaction': 'Успешно'}
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Доступ запрещен'
        )


@router.get('/{category_slug}')
async def product_by_category(db: Annotated[AsyncSession, Depends(get_db)], category_slug: str):
    # Метод получения товаров по категории
    category = await db.scalar(select(Category).where(Category.slug == category_slug))
    if not category:
        raise HTTPException(status_code=404, detail='Категория не найдена')

    subcategories = await db.scalars(select(Category).where(Category.parent_id == category.id))
    categories_ids = [category.id] + [sub.id for sub in subcategories.all()]

    products = await db.scalars(
        select(Product).where(
            Product.category_id.in_(categories_ids),
            Product.is_active == True,
            Product.stock > 0
        ))
    return products.all()


@router.get('/detail/{product_slug}')
async def product_detail(db: Annotated[AsyncSession, Depends(get_db)], product_slug: str):
    # Метод получения деталей товара
    product = await db.scalar(
        select(Product).where(
            Product.slug == product_slug,
            Product.is_active == True,
            Product.stock > 0
        ))
    if not product:
        raise HTTPException(status_code=404, detail='Товар не найден')
    return product


@router.put('/detail/{product_slug}')
async def update_product(
        db: Annotated[AsyncSession, Depends(get_db)],
        product_slug: str,
        update_data: CreateProduct,
        user: Annotated[dict, Depends(get_current_user)]
):
    # Метод обновления товара
    product = await db.scalar(select(Product).where(Product.slug == product_slug))
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    new_slug = slugify(update_data.name)
    if new_slug != product_slug:
        existing = await db.scalar(select(Product).where(Product.slug == new_slug))
        if existing:
            raise HTTPException(status_code=400, detail="Товар с таким именем уже существует")

    if user['id'] == product.supplier_id or user.get('is_admin'):
        await db.execute(
            update(Product)
            .where(Product.slug == product_slug)
            .values(
                name=update_data.name,
                description=update_data.description,
                price=update_data.price,
                image_url=update_data.image_url,
                stock=update_data.stock,
                category_id=update_data.category_id,  # Исправлено имя поля
                slug=new_slug
            ))
        await db.commit()
        return {"status": "Товар успешно обновлен"}
    else:
        raise HTTPException(status_code=403, detail="Нет доступа")


@router.delete('/delete/{product_id}')
async def delete_product(
        db: Annotated[AsyncSession, Depends(get_db)],
        product_id: int,
        user: Annotated[dict, Depends(get_current_user)]
):
    # Метод удаления товара
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    if user['id'] == product.supplier_id or user.get('is_admin'):
        await db.execute(update(Product).where(Product.id == product_id).values(is_active=False))
        await db.commit()
        return {"status": "Товар удален"}
    else:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession  # Исправлено: AsyncSession вместо Session
from sqlalchemy.exc import IntegrityError  # Добавлена обработка ошибок БД
from app.models.user import User
from app.schemas import CreateUser
from app.backend.db_depends import get_db
from typing import Annotated
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

router = APIRouter(prefix='/auth', tags=['auth'])
bcrypt_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

SECRET_KEY = '50a929ea9e25d8eeca854fe8234328d3ce14b92dec1e04205fcbc3f1526b5acf'
ALGORITHM = 'HS256'


# ----------------------------
# РОУТ: Регистрация пользователя
# ----------------------------
@router.post('/')
async def create_user(
        db: Annotated[AsyncSession, Depends(get_db)],  # Исправлено: AsyncSession
        create_user: CreateUser
):
    try:
        await db.execute(
            insert(User).values(
                first_name=create_user.first_name,
                last_name=create_user.last_name,
                username=create_user.username,
                email=create_user.email,
                hashed_password=bcrypt_context.hash(create_user.password),
                is_active=True,  # Добавлены обязательные поля
                is_admin=False,
                is_supplier=False,
                is_customer=True
            )
        )
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail="User with this email or username already exists"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    return {'status_code': 201, 'transaction': 'Successful'}


# ----------------------------
# Аутентификация пользователя
# ----------------------------
async def authenticate_user(  # Исправлено название функции
        db: Annotated[AsyncSession, Depends(get_db)],
        username: str,
        password: str
):
    user = await db.scalar(select(User).where(User.username == username))

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username")
    if not bcrypt_context.verify(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")
    if not user.is_active:  # Улучшенная проверка активности
        raise HTTPException(status_code=403, detail="Inactive user")

    return user


# ----------------------------
# Генерация токена
# ----------------------------
async def create_access_token(
        username: str,
        user_id: int,
        expires_delta: timedelta,
        is_admin: bool = False,
        is_supplier: bool = False,
        is_customer: bool = True
):
    encode = {
        'sub': username,
        'id': user_id,
        'is_admin': is_admin,
        'is_supplier': is_supplier,
        'is_customer': is_customer,
    }
    expire = datetime.now(timezone.utc) + expires_delta
    encode.update({'exp': expire})
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)


# ----------------------------
# РОУТ: Логин
# ----------------------------
@router.post('/token')
async def login(
        db: Annotated[AsyncSession, Depends(get_db)],
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    user = await authenticate_user(db, form_data.username, form_data.password)  # Исправлен вызов функции
    token = await create_access_token(
        username=user.username,
        user_id=user.id,
        expires_delta=timedelta(minutes=20),
        is_admin=user.is_admin,
        is_supplier=user.is_supplier,
        is_customer=user.is_customer
    )
    return {'access_token': token, 'token_type': 'bearer'}


# ----------------------------
# Получение текущего пользователя
# ----------------------------
async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get('sub')
        user_id = payload.get('id')

        if not username or not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Корректная проверка времени
        expire = payload.get('exp')
        if datetime.now(timezone.utc) > datetime.fromtimestamp(expire, tz=timezone.utc):
            raise HTTPException(status_code=403, detail="Token expired")

        return {
            'username': username,
            'id': user_id,
            'is_admin': payload.get('is_admin', False),
            'is_supplier': payload.get('is_supplier', False),
            'is_customer': payload.get('is_customer', True)
        }

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ----------------------------
# Информация о пользователе
# ----------------------------
@router.get('/read_current_user')
async def read_current_user(user: dict = Depends(get_current_user)):  # Исправлен тип
    return {'user': user}
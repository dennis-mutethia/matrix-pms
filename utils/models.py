from typing import Optional
from datetime import datetime
from uuid import UUID
from sqlalchemy import func
from sqlmodel import SQLModel, Field

class User_Levels(SQLModel, table=True):
    id: UUID = Field(
        primary_key=True,
        index=True,                
        nullable=False,
        sa_column_kwargs={"server_default": func.gen_random_uuid()}
    )
    name: str
    level: int = 0
    description: Optional[str] = None
    created_at: datetime = Field(nullable=False)
    created_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
    
class Landlords(SQLModel, table=True):
    id: UUID = Field(
        primary_key=True,
        index=True,                
        nullable=False,
        sa_column_kwargs={"server_default": func.gen_random_uuid()}
    )
    name: str
    phone: str = Field(
        unique=True, 
        index=True
    )
    id_number: str = Field(
        unique=True, 
        index=True
    )
    email: str
    kra_pin: Optional[str]
    address: Optional[str]
    bank_name: Optional[str]
    bank_account: Optional[str]
    commission_rate: Optional[float]    
    status: str = "active"
    created_at: datetime = Field(nullable=False)
    created_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
     
class Users(SQLModel, table=True):
    id: UUID = Field(
        primary_key=True,
        index=True,                
        nullable=False,
        sa_column_kwargs={"server_default": func.gen_random_uuid()}
    )
    name: str
    phone: str = Field(
        unique=True, 
        index=True
    )
    user_level_id: UUID = Field(
        foreign_key="user_levels.id", 
        index=True        
    )
    landlord_id: UUID = Field(
        foreign_key="landlords.id", 
        index=True
    )     
    apartment_id: Optional[UUID] = Field(
        default=None,
        foreign_key="apartments.id",
        index=True,
        nullable=True
    )
    password: str
    status: str = "active"
    created_at: datetime = Field(nullable=False)
    created_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
        
class Packages(SQLModel, table=True):
    id: UUID = Field(
        primary_key=True,
        index=True,                
        nullable=False,
        sa_column_kwargs={"server_default": func.gen_random_uuid()}
    )
    name: str
    amount: float
    pay: float
    validity: int
    color: str = None
    description: Optional[str] = None
    offer: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
    
class Licenses(SQLModel, table=True):
    id: UUID = Field(
        primary_key=True,
        index=True,                
        nullable=False,
        sa_column_kwargs={"server_default": func.gen_random_uuid()}
    )
    key: str
    package_id: UUID = Field(
        foreign_key="packages.id", 
        index=True
    )    
    landlord_id: UUID = Field(
        foreign_key="landlords.id", 
        index=True
    )      
    expires_at: datetime
    created_at: datetime = Field(nullable=False)
    created_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
                    
class Apartments(SQLModel, table=True):
    id: UUID = Field(
        primary_key=True,
        index=True,                
        nullable=False,
        sa_column_kwargs={"server_default": func.gen_random_uuid()}
    )
    name: str
    location: str
    landlord_id: UUID = Field(
        foreign_key="landlords.id", 
        index=True
    )     
    created_at: datetime = Field(nullable=False)
    created_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[UUID] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True
    )
     
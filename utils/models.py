
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field

class User_Levels(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True
    )
    name: str
    level: int = 0
    description: Optional[str]
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False
    )
    created_by: UUID 
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]

class Landlords(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True
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
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False
    )
    created_by: UUID 
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]
        
class Users(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True
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
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False
    )
    created_by: UUID 
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]
        
class Packages(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True
    )
    name: str
    amount: float
    pay: float
    validity: int
    color: str = None
    description: Optional[str]
    offer: Optional[str]
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False
    )
    created_by: UUID 
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]
    
class Licenses(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True
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
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False
    )
    created_by: UUID 
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]
                    
class Apartments(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True
    )
    name: str
    location: str
    landlord_id: UUID = Field(
        foreign_key="landlords.id", 
        index=True
    )    
    status: str = "active" 
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False
    )
    created_by: UUID 
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]
                    
class House_Units(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True
    )
    name: str
    apartment_id: UUID = Field(
        foreign_key="apartments.id", 
        index=True
    )   
    rent: float 
    rent_deposit: Optional[float]
    water_deposit: Optional[float]
    electricity_deposit: Optional[float]
    other_deposits: Optional[float] 
    status: str = "active"
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False
    )
    created_by: UUID 
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]

class Tenants(SQLModel, table=True):
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True
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
    house_unit_id: Optional[UUID] = Field(
        foreign_key="house_units.id", 
        index=True
    )   
    next_of_kin: Optional[str]
    next_of_kin_phone: Optional[str]
    occupation: Optional[str]
    employer: Optional[str]
    status: str = "unassigned"
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False
    )
    created_by: UUID 
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]
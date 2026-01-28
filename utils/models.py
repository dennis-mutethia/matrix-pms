from typing import Optional
from datetime import date, datetime
from sqlmodel import SQLModel, Field

class User_Levels(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    level: int = 0
    description: Optional[str] = None
    created_at: datetime = Field(nullable=False)
    created_by: int = 0
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[int] = None

class Users(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    phone: str
    apartment_id: int
    user_level_id: int = 0
    password: str
    created_at: datetime = Field(nullable=False)
    created_by: int = 0
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[int] = None
        
class Packages(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    amount: float
    pay: float
    validity: int
    color: str = None
    description: Optional[str] = None
    offer: Optional[str] = None
    created_at: Optional[str] = None
    created_by: int = 0
    updated_at: Optional[datetime] = None
    updated_by: Optional[int] = None
    
class Licenses(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str
    package_id: int
    expires_at: datetime
    payment_id: int
    created_at: datetime = Field(nullable=False)
    created_by: int = 0
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[int] = None 
                
class Landlords(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str
    phone: str
    id_number: str
    kra_pin: Optional[str]
    address: Optional[str]
    bank_name: Optional[str]
    bank_account: Optional[str]
    commission_rate: Optional[float]    
    status: str = "active"
    license_id: int = None
    created_at: datetime = Field(nullable=False)
    created_by: int = 0
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[int] = None    
                
class Apartments(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    location: str
    landlord_id: int = None
    created_at: datetime = Field(nullable=False)
    created_by: int = 0
    updated_at: Optional[datetime] = Field()
    updated_by: Optional[int] = None    
     
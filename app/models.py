from . import db
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key = True)
    fname = db.Column(db.String(150), nullable=False)
    lname = db.Column(db.String(150), nullable=False)
    gender = db.Column(db.String(15), nullable=False)
    username = db.Column(db.String(150), nullable=False, unique=True)
    address = db.Column(db.String(150), nullable=True)
    dob = db.Column(db.Date, nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    phone = db.Column(db.String(50), nullable=False)
    city = db.Column(db.String(150), nullable=False)
    state = db.Column(db.String(150), nullable=False)
    zip = db.Column(db.String(150), nullable=False)
    password = db.Column(db.String(150), nullable=False)
    profile_img = db.Column(db.String(120), default="default_male.jpg")

    def __init__(self, gender, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if gender == "female":
            self.profile_img = "default_female.png"
        elif gender == "male":
            self.profile_img = "default_male.jpg"
        else:
            self.profile_img = "default_custom.jpg"
        self.gender = gender
    
    def __repr__(self) -> str:
        return f"<user {self.username}>"
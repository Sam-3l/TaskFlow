from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, DateField, EmailField, TelField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError

class SignupForm(FlaskForm):
    fname = StringField("First Name", validators=[DataRequired(), Length(min=2, max=150),], render_kw={"placeholder":"First name", "class":"form-control"})
    lname = StringField("Last Name", validators=[DataRequired(), Length(min=2, max=150),], render_kw={"placeholder":"Last name", "class":"form-control"})
    gender = SelectField("Gender", validators=[DataRequired(), Length(min=2, max=150),], choices=[("select", "Select Your Gender"), ("male", "Male"), ("female", "Female"), ("custom", "Custom")], render_kw={"class":"form-select", "onchange": "displayoff('gender_err')"})
    username = StringField("Username", validators=[DataRequired(), Length(min=6, max=150),], render_kw={"placeholder":"Username", "class":"form-control", "oninput": "displayoff('uname_err', this)", "id":"username"}) 
    address = StringField("Address", validators=[DataRequired(), Length(min=4, max=150),], render_kw={"placeholder":"1234 Main St", "class":"form-control"})
    dob = DateField("Date Of Birth", validators=[DataRequired(),], render_kw={"class":"form-control", "onchange": "displayoff('dob_err')"})
    email = EmailField("Email", validators=[DataRequired(), Length(max=150),], render_kw={"placeholder":"myname@example.com", "class":"form-control", "oninput": "displayoff('email_err')"})
    phone = TelField("Phone Number", validators=[DataRequired(), Length(min=6, max=150),], render_kw={"placeholder":"(+44) 2537 1377", "class":"form-control"})
    city = StringField("City", validators=[DataRequired(), Length(max=150),], render_kw={"placeholder":"New York", "class":"form-control"})
    state = StringField("State", validators=[DataRequired(), Length(max=150),], render_kw={"placeholder":"Washinton D.C", "class":"form-control"})
    zip = StringField("Zip", validators=[DataRequired(), Length(max=50),], render_kw={"class":"form-control"})
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=150),], render_kw={"placeholder":"Input your password", "class":"form-control"})
    c_pass = PasswordField("Confirm Password", validators=[DataRequired(), Length(min=8, max=150), EqualTo("password"),], render_kw={"placeholder":"Confirm your password", "class":"form-control", "oninput": "displayoff('cpass_err')"})
    check = BooleanField("I agree to the terms and conitions and privacy policy", validators=[DataRequired(),], render_kw={"class":"form-check-input"})
    submit = SubmitField("Sign up", render_kw={"class": "btn btn-secondary"})

    def validate_username(self, field):
        from .models import User
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("This username is already taken. Please choose another.")

    def validate_gender(self, field):
        if field.data == "select":
            raise ValidationError("Please select a vaild gender.")

    def validate_email(self, field):
        from .models import User
        if User.query.filter_by(email=field.data).first():
            raise ValidationError("An account was found with this email.")

class LoginForm(FlaskForm):
    uname_or_email = StringField("Username Or Email", validators=[DataRequired(),], render_kw={"placeholder":"Enter your username or email", "class":"form-control", "oninput": "displayoff('uname_email_err')",})
    password = PasswordField("Input Your Password", validators=[DataRequired(),], render_kw={"placeholder":"Enter your password", "class":"form-control", "oninput": "displayoff('uname_email_err')",})
    remember = BooleanField("Remember me", render_kw={"class":"form-check-input"},)
    submit = SubmitField("Login", render_kw={"class":"btn btn-secondary w-100"})

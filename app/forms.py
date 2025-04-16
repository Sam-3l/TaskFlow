from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import SelectField, StringField, DateField, EmailField, TelField, PasswordField, BooleanField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Optional

class MyDateField(DateField):
    def process_formdata(self, valuelist):
        if valuelist:
            if valuelist[0] == 'mm/dd/yyyy' or valuelist[0] == '':
                self.data = None
            else:
                super().process_formdata(valuelist)

class SignupForm(FlaskForm):
    fname = StringField("First Name", validators=[DataRequired(), Length(min=2, max=150),], render_kw={"placeholder":"First name", "class":"form-control"})
    lname = StringField("Last Name", validators=[DataRequired(), Length(min=2, max=150),], render_kw={"placeholder":"Last name", "class":"form-control"})
    username = StringField("Username", validators=[DataRequired(), Length(min=6, max=150),], render_kw={"placeholder":"Username", "class":"form-control", "oninput": "displayoff('uname_err', this)", "id":"username"}) 
    email = EmailField("Email", validators=[DataRequired(), Length(max=150),], render_kw={"placeholder":"myname@example.com", "class":"form-control", "oninput": "displayoff('email_err')"})
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=150),], render_kw={"placeholder":"Input your password", "class":"form-control"})
    c_pass = PasswordField("Confirm Password", validators=[DataRequired(), Length(min=8, max=150), EqualTo("password"),], render_kw={"placeholder":"Confirm your password", "class":"form-control", "oninput": "displayoff('cpass_err')"})
    check = BooleanField("I agree to the terms and conitions and privacy policy", validators=[DataRequired(),], render_kw={"class":"form-check-input"})
    submit = SubmitField("Sign up", render_kw={"class": "btn btn-secondary w-100"})

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

class CreateTask(FlaskForm):
    title = StringField("Title:", validators=[DataRequired(), Length(min=3, max=60),], render_kw={"placeholder":"Name your task",})
    description = TextAreaField("Description:", validators=[DataRequired(), Length(min=4, max=245),], render_kw={"placeholder":"Enter description"})
    priority = SelectField("Priority:", validators=[DataRequired(), Length(min=2, max=150),], choices=[("critical", "Critical"), ("high-priority", "High priority"), ("medium-priority", "Medium priority"), ("low-priority", "Low priority"), ("optional", "Optional")])
    deadline = MyDateField("Deadline date:", validators=[Optional()])
    submit = SubmitField("Create Task")

class CreateProject(FlaskForm):
    title = StringField("Title:", validators=[DataRequired(), Length(min=3, max=60),], render_kw={"placeholder":"Name your project"})
    description = TextAreaField("Description:", validators=[DataRequired(), Length(min=4, max=255),], render_kw={"placeholder":"Describe your project"})
    type = SelectField("Project Type:", validators=[DataRequired()], choices=[
        ("private", "Private - Only manager can add members"),
        ("public", "Public - Anyone can request to join")
    ])
    project_links = StringField("Project Links:", validators=[Optional(), Length(max=255)], render_kw={"placeholder":"Add relevant links (comma-separated)"})
    cover_image = FileField("Cover Image:", validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'webp', 'svg', 'bmp', 'tiff'], 'Images only!')
    ])
    submit = SubmitField("Create Project")
    
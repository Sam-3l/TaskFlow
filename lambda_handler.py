from mangum import Mangum
from manage import app

handler = Mangum(app)
from flask_wtf import FlaskForm
from wtforms import StringField, RadioField, FileField, HiddenField
from wtforms.fields.html5 import DateTimeField
from wtforms.validators import DataRequired, Optional


class NewCollectorForm(FlaskForm):
    trigger = RadioField('Triggered', default='background',
                         choices=[('background', 'Background'), ('manual', 'Manual'), ('on-demand', 'On Demand')],
                         validators=[DataRequired('You must declare how collection was triggered.')]
                         )
    config = FileField('Upload your config file', validators=[DataRequired('Collector configuration is mandatory.')])
    kwfile = FileField('Upload keywords file')
    locfile = FileField('Upload locations file')
    forecast_id = StringField('Forecast Id')
    runtime = DateTimeField('Run until...', format='%Y-%m-%d %H:%M', validators=(Optional(),))
    nuts3 = StringField('NUTS3 Code')
    nuts3source = StringField('NUTS3 Source')
    tzclient = HiddenField('tzclient')

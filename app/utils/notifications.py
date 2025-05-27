from datetime import datetime
from flask import current_app
from app.models import Notification, db, User

def add_notification(user_id, message, link=None, icon=None, sender_id=None):
    """
    Add a new notification for a user
    """
    try:
        notification = Notification(
            user_id=user_id,
            message=message,
            link=link,
            icon=icon,
            sender_id=sender_id
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    except Exception as e:
        current_app.logger.error(f"Failed to add notification: {str(e)}")
        db.session.rollback()
        return None

def get_unread_count(user_id):
    """
    Get count of unread notifications for a user
    """
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()

def mark_notifications_as_read(user_id, notification_ids=None):
    """
    Mark notifications as read
    If notification_ids is None, mark all as read
    """
    try:
        query = Notification.query.filter_by(user_id=user_id, is_read=False)
        if notification_ids:
            query = query.filter(Notification.id.in_(notification_ids))
        
        query.update({'is_read': True})
        db.session.commit()
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to mark notifications as read: {str(e)}")
        db.session.rollback()
        return False

def get_user_notifications(user_id, limit=20):
    """
    Get user notifications sorted by latest first
    """
    return Notification.query.filter_by(user_id=user_id)\
        .order_by(Notification.created_at.desc())\
        .limit(limit)\
        .all()
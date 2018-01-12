import logging
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.dispatch import receiver
from django.db.models.signals import pre_delete, post_delete, post_save

from mlarchive.archive.models import Message, EmailList

logger = logging.getLogger('mlarchive.custom')


@receiver([post_save, post_delete], sender=EmailList)
def _clear_lists_cache(sender, instance, **kwargs):
    """If EmailList object is saved or deleted remove the list_info cache entry
    """
    cache.delete('lists')
    cache.delete('lists_public')

@receiver(user_logged_in)
def _clear_session(sender, request, user, **kwargs):
    """Clear the cached session['noauth'] on login because it will change
    if the user is a member of a private list.  No need to do this on
    logout because logout() does a session flush
    """
    if 'noauth' in request.session:
        del request.session['noauth']


@receiver(pre_delete, sender=Message)
def _message_remove(sender, instance, **kwargs):
    """When messages are removed, via the admin page, we need to move the message
    archive file to the "_removed" directory
    """
    path = instance.get_file_path()
    if not os.path.exists(path):
        return
    target = instance.get_removed_dir()
    if not os.path.exists(target):
        os.mkdir(target)
        os.chmod(target, 02777)
    shutil.move(path, target)
    logger.info('message file moved: {} => {}'.format(path, target))

    # if message is first of many in thread, should reset thread.first before
    # deleting
    if (instance.thread.first == instance and
            instance.thread.message_set.count() > 1):
        next_in_thread = instance.thread.message_set.order_by('date')[1]
        instance.thread.set_first(next_in_thread)


@receiver(post_save, sender=Message)
def _message_save(sender, instance, **kwargs):
    """When messages are saved, udpate thread info
    """
    if not instance.thread.first or instance.date < instance.thread.date:
        instance.thread.set_first(instance)


@receiver(post_save, sender=EmailList)
def _list_save_handler(sender, instance, **kwargs):
    _export_lists()


def _export_lists():
    """Write XML dump of list / memberships and call external program"""
    
    # Dump XML
    data = _get_lists_as_xml()
    path = os.path.join(settings.EXPORT_DIR, 'email_lists.xml')
    try:
        if not os.path.exists(settings.EXPORT_DIR):
            os.mkdir(settings.EXPORT_DIR)
        with open(path, 'w') as file:
            file.write(data)
            os.chmod(path, 0666)
    except Exception as error:
        logger.error('Error creating export file: {}'.format(error))
        return

    # Call external script
    if hasattr(settings, 'NOTIFY_LIST_CHANGE_COMMAND'):
        command = settings.NOTIFY_LIST_CHANGE_COMMAND
        try:
            subprocess.check_call([command, path])
        except (OSError, subprocess.CalledProcessError) as error:
            logger.error(
                'Error calling external command: {} ({})'.format(
                    command, error))


def _get_lists_as_xml():
    """Returns string: XML of lists / membership for IMAP"""
    lines = []
    lines.append("<ms_config>")

    for elist in EmailList.objects.all().order_by('name'):
        lines.append("  <shared_root name='{name}' path='/var/isode/ms/shared/{name}'>".format(name=elist.name))
        if elist.private:
            lines.append("    <user name='anonymous' access='none'/>")
            for member in elist.members.all():
                lines.append("    <user name='{name}' access='read,write'/>".format(name=member.username))
        else:
            lines.append("    <user name='anonymous' access='read'/>")
            lines.append("    <group name='anyone' access='read,write'/>")
        lines.append("  </shared_root>")
    lines.append("</ms_config>")
    return "\n".join(lines)
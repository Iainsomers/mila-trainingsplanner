"""Consistent author initials and colors in coach comment blocks."""
import colorsys


def decorate_coach_comment(item):
    username_parts = [part for part in item.coach.get_username().split('_') if part]
    full_name = (item.coach.get_full_name() or '').split()
    parts = username_parts if len(username_parts) > 1 else full_name
    item.initials = ((parts[0][:1] + parts[-1][:1]) if len(parts) > 1
                     else (parts[0][:2] if parts else item.coach.get_username()[:2])).upper()
    hue = ((item.coach_id * 137.508) % 360) / 360
    red, green, blue = colorsys.hls_to_rgb(hue, .32, .62)
    item.coach_color = '#%02x%02x%02x' % (round(red*255), round(green*255), round(blue*255))
    return item
